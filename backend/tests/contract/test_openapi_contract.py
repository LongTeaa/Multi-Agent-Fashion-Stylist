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

    def test_stylist_chat_operation_contract(self, openapi_schema: dict) -> None:
        paths = openapi_schema.get("paths", {})
        assert "/api/v1/stylist/chat" in paths, "Route /api/v1/stylist/chat must be present in OpenAPI paths."
        post_op = paths["/api/v1/stylist/chat"].get("post")
        assert post_op is not None, "POST operation must be defined on /api/v1/stylist/chat."

        # Verify X-User-Id header parameter
        parameters = post_op.get("parameters", [])
        user_id_param = next(
            (p for p in parameters if p.get("name") == "X-User-Id" and p.get("in") == "header"),
            None,
        )
        assert user_id_param is not None, "X-User-Id header parameter must be documented."

        # Verify requestBody
        request_body = post_op.get("requestBody")
        assert request_body is not None, "POST /api/v1/stylist/chat must contain requestBody."
        content = request_body.get("content", {})
        assert "application/json" in content

        # Verify responses: 200, 404, 422, 502
        responses = post_op.get("responses", {})
        assert "200" in responses, "HTTP 200 response must be documented."
        for err_code in ("404", "422", "502"):
            assert err_code in responses, f"HTTP {err_code} error response must be documented."
            err_content = responses[err_code].get("content", {}).get("application/json", {}).get("schema", {})
            assert "ErrorResponse" in err_content.get("$ref", "")

        # Verify schemas: check StylistChatResponseData and StylistRecommendationResponse
        schemas = openapi_schema.get("components", {}).get("schemas", {})
        assert "StylistChatResponseData" in schemas
        chat_data_schema = schemas["StylistChatResponseData"]
        props = chat_data_schema.get("properties", {})
        for expected_prop in [
            "request_id",
            "needs_clarification",
            "clarification_question",
            "context",
            "recommendations",
            "feedback_prompt_eligible",
            "feedback_target_outfit_id",
            "warnings",
        ]:
            assert expected_prop in props, f"StylistChatResponseData must include {expected_prop}."

        assert "StylistRecommendationItemResponse" in schemas
        item_schema = schemas["StylistRecommendationItemResponse"]
        item_props = item_schema.get("properties", {})
        assert "slot" in item_props
        assert "item_id" in item_props
        assert "name" in item_props
        assert "image_url" in item_props
        # Ensure raw storage keys are NOT exposed
        assert "object_key" not in item_props
        assert "bucket" not in item_props

        # Verify StylistRecommendationResponse constraints
        assert "StylistRecommendationResponse" in schemas
        rec_schema = schemas["StylistRecommendationResponse"]
        rec_props = rec_schema.get("properties", {})
        assert "rank" in rec_props
        assert rec_props["rank"].get("minimum") == 1
        assert rec_props["rank"].get("maximum") == 3
        assert "composite_score" in rec_props
        assert rec_props["composite_score"].get("minimum") == 0.0
        assert rec_props["composite_score"].get("maximum") == 1.0

        # Verify StylistChatRequest schema includes client_session_id
        assert "StylistChatRequest" in schemas
        chat_req_props = schemas["StylistChatRequest"].get("properties", {})
        assert "client_session_id" in chat_req_props, "StylistChatRequest must include 'client_session_id'."

    def test_outfit_actions_operations_exist(self, openapi_schema: dict) -> None:
        paths = openapi_schema.get("paths", {})
        expected_endpoints = {
            "/api/v1/outfits/saved": ["get"],
            "/api/v1/outfits/{outfit_id}": ["get"],
            "/api/v1/outfits/{outfit_id}/bookmark": ["put"],
            "/api/v1/outfits/{outfit_id}/worn": ["post"],
            "/api/v1/outfits/{outfit_id}/rating": ["put"],
            "/api/v1/feedback/prompts/dismiss": ["post"],
        }
        for endpoint, methods in expected_endpoints.items():
            assert endpoint in paths, f"Route {endpoint} must be present in OpenAPI paths."
            for method in methods:
                op = paths[endpoint].get(method)
                assert op is not None, f"{method.upper()} operation must be defined on {endpoint}."

                parameters = op.get("parameters", [])
                user_id_param = next(
                    (p for p in parameters if p.get("name") == "X-User-Id" and p.get("in") == "header"),
                    None,
                )
                assert user_id_param is not None, f"X-User-Id header parameter must be documented on {method.upper()} {endpoint}."

                # Verify 404 response is documented for single outfit operations
                if "{outfit_id}" in endpoint:
                    responses = op.get("responses", {})
                    assert "404" in responses, f"HTTP 404 response must be documented on {method.upper()} {endpoint}."
                    err_content = responses["404"].get("content", {}).get("application/json", {}).get("schema", {})
                    assert "ErrorResponse" in err_content.get("$ref", "")

    def test_tryon_operation_and_response_contract(self, openapi_schema: dict) -> None:
        paths = openapi_schema.get("paths", {})
        assert "/api/v1/tryons" in paths
        operation = paths["/api/v1/tryons"].get("post")
        assert operation is not None

        parameters = operation.get("parameters", [])
        assert any(
            parameter.get("name") == "X-User-Id" and parameter.get("in") == "header"
            for parameter in parameters
        )
        for status_code in ("200", "404", "422", "504"):
            assert status_code in operation.get("responses", {})

        schemas = openapi_schema.get("components", {}).get("schemas", {})
        assert set(schemas["TryOnRequest"].get("properties", {})) == {"outfit_id"}
        response_properties = schemas["TryOnResponseData"].get("properties", {})
        assert set(response_properties) == {
            "tryon_id",
            "outfit_id",
            "image_url",
            "render_kind",
            "fallback_used",
            "duration_ms",
            "status",
        }
        assert "object_key" not in response_properties
        assert "bucket" not in response_properties

    def test_outfit_actions_request_and_response_schemas(self, openapi_schema: dict) -> None:
        schemas = openapi_schema.get("components", {}).get("schemas", {})

        # 1. Bookmark request
        assert "BookmarkOutfitRequest" in schemas
        bookmark_props = schemas["BookmarkOutfitRequest"].get("properties", {})
        assert "is_bookmarked" in bookmark_props
        assert "is_bookmarked" in schemas["BookmarkOutfitRequest"].get("required", [])

        # 2. Worn request
        assert "WornOutfitRequest" in schemas
        worn_props = schemas["WornOutfitRequest"].get("properties", {})
        assert "idempotency_key" in worn_props
        assert "idempotency_key" in schemas["WornOutfitRequest"].get("required", [])
        assert "worn_at" in worn_props

        # 3. Rating request
        assert "OutfitRatingRequest" in schemas
        rating_props = schemas["OutfitRatingRequest"].get("properties", {})
        assert "stars" in rating_props
        assert rating_props["stars"].get("minimum") == 1
        assert rating_props["stars"].get("maximum") == 5
        assert "source" in rating_props
        assert "client_session_id" in rating_props

        # 4. Dismiss prompt request
        assert "DismissPromptRequest" in schemas
        dismiss_props = schemas["DismissPromptRequest"].get("properties", {})
        assert "client_session_id" in dismiss_props

        # 5. Outfit detail response data
        assert "OutfitDetailResponseData" in schemas
        detail_props = schemas["OutfitDetailResponseData"].get("properties", {})
        for field in [
            "id",
            "request_id",
            "user_query",
            "explanation_vi",
            "fashion_score",
            "personalization_score",
            "composite_score",
            "rank",
            "is_bookmarked",
            "times_worn",
            "last_worn_at",
            "user_rating",
            "items",
            "created_at",
        ]:
            assert field in detail_props, f"OutfitDetailResponseData must include '{field}'."

        # 6. Outfit item detail response
        assert "OutfitItemDetailResponse" in schemas
        item_props = schemas["OutfitItemDetailResponse"].get("properties", {})
        for field in [
            "slot_role",
            "wardrobe_item_id",
            "name",
            "category",
            "sub_category",
            "primary_color",
            "secondary_color",
            "pattern",
            "material",
            "style",
            "image_url",
            "is_active",
        ]:
            assert field in item_props, f"OutfitItemDetailResponse must include '{field}'."
        assert "object_key" not in item_props, "Raw object_key must not be exposed."
        assert "bucket" not in item_props, "Raw bucket must not be exposed."

        # 7. Saved outfits response data
        assert "SavedOutfitsResponseData" in schemas
        saved_props = schemas["SavedOutfitsResponseData"].get("properties", {})
        assert "items" in saved_props
        assert "page" in saved_props
        assert "page_size" in saved_props
        assert "total" in saved_props

    def test_strictly_no_like_dislike_endpoints_or_fields(self, openapi_schema: dict) -> None:
        """INVARIANT: The MVP MUST NOT expose Like/Dislike endpoints or fields."""
        paths = openapi_schema.get("paths", {})
        for path in paths:
            assert "like" not in path.lower(), f"Endpoint path '{path}' contains forbidden word 'like'."
            assert "dislike" not in path.lower(), f"Endpoint path '{path}' contains forbidden word 'dislike'."

        schemas = openapi_schema.get("components", {}).get("schemas", {})
        for schema_name, schema_body in schemas.items():
            assert "like" not in schema_name.lower(), f"Schema '{schema_name}' contains forbidden word 'like'."
            assert "dislike" not in schema_name.lower(), f"Schema '{schema_name}' contains forbidden word 'dislike'."
            properties = schema_body.get("properties", {})
            for prop in properties:
                assert prop.lower() not in {"like", "dislike", "is_liked", "is_disliked", "thumbs_up", "thumbs_down"}, (
                    f"Property '{prop}' in schema '{schema_name}' violates no-like/dislike invariant."
                )
