from __future__ import annotations

import pytest

from app.main import app
from app.models.entities import InputKind


class TestOpenAPIContract:
    @pytest.fixture(scope="class")
    def openapi_schema(self) -> dict:
        return app.openapi()

    def test_ingestion_upload_operation_exists(self, openapi_schema: dict) -> None:
        paths = openapi_schema.get("paths", {})
        assert "/api/v1/ingestions" in paths, "Route /api/v1/ingestions must be present in OpenAPI paths."
        post_op = paths["/api/v1/ingestions"].get("post")
        assert post_op is not None, "POST operation must be defined on /api/v1/ingestions."

    def test_profile_operations_exist(self, openapi_schema: dict) -> None:
        paths = openapi_schema.get("paths", {})
        assert "get" in paths["/api/v1/user/profile"]
        assert "put" in paths["/api/v1/user/profile/preferences"]
        assert "get" in paths["/api/v1/user/profile/preference-options"]

    def test_ingestion_upload_multipart_request_body(self, openapi_schema: dict) -> None:
        post_op = openapi_schema["paths"]["/api/v1/ingestions"]["post"]
        request_body = post_op.get("requestBody")
        assert request_body is not None, "POST /api/v1/ingestions must contain requestBody specification."
        assert request_body.get("required") is True

        content = request_body.get("content", {})
        assert "multipart/form-data" in content, "Request body content must include 'multipart/form-data'."

        body_schema_ref = content["multipart/form-data"].get("schema", {})
        ref_path = body_schema_ref.get("$ref")
        assert ref_path is not None, "Multipart form data must reference a schema."

        schema_key = ref_path.split("/")[-1]
        schemas = openapi_schema.get("components", {}).get("schemas", {})
        assert schema_key in schemas, f"Schema {schema_key} must exist in components.schemas."

        form_schema = schemas[schema_key]
        properties = form_schema.get("properties", {})

        # Verify images[] field
        assert "images[]" in properties, "Schema must include 'images[]' property."
        images_prop = properties["images[]"]
        assert images_prop.get("type") == "array", "'images[]' must be typed as an array."
        items = images_prop.get("items", {})
        # FastAPI / OpenAPI represents file uploads with type string and format binary or contentMediaType
        assert items.get("type") == "string"
        assert items.get("format") == "binary" or items.get("contentMediaType") == "application/octet-stream"

        required_fields = form_schema.get("required", [])
        assert "images[]" in required_fields, "'images[]' must be a required field."

        # Verify declared_input_kind field
        assert "declared_input_kind" in properties, "Schema must include 'declared_input_kind' property."
        kind_prop = properties["declared_input_kind"]

        # Check enum values against InputKind
        canonical_enum_values = {k.value for k in InputKind}
        if "$ref" in kind_prop:
            enum_key = kind_prop["$ref"].split("/")[-1]
            enum_schema = schemas.get(enum_key, {})
            assert set(enum_schema.get("enum", [])) == canonical_enum_values
        elif "anyOf" in kind_prop:
            ref_item = next((item for item in kind_prop["anyOf"] if "$ref" in item), None)
            assert ref_item is not None, "declared_input_kind must reference InputKind enum."
            enum_key = ref_item["$ref"].split("/")[-1]
            enum_schema = schemas.get(enum_key, {})
            assert set(enum_schema.get("enum", [])) == canonical_enum_values

    def test_ingestion_upload_responses_contract(self, openapi_schema: dict) -> None:
        post_op = openapi_schema["paths"]["/api/v1/ingestions"]["post"]
        responses = post_op.get("responses", {})

        # Successful response: HTTP 202
        assert "202" in responses, "HTTP 202 response must be documented."
        res_202 = responses["202"]
        content_202 = res_202.get("content", {}).get("application/json", {}).get("schema", {})
        ref_202 = content_202.get("$ref", "")
        assert "SuccessResponse" in ref_202 or "IngestionUploadResponseData" in ref_202

        # Error envelopes: HTTP 400 and 422
        for err_status in ("400", "422"):
            assert err_status in responses, f"HTTP {err_status} response must be documented."
            err_content = responses[err_status].get("content", {}).get("application/json", {}).get("schema", {})
            assert "ErrorResponse" in err_content.get("$ref", "")
