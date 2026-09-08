from __future__ import annotations

from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: DataT


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


class AppException(Exception):
    """Base application exception mapping to standard API error envelopes."""

    status_code: int = 400
    code: str = "APPLICATION_ERROR"
    message: str = "Đã xảy ra lỗi trong quá trình xử lý."

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class ValidationError(AppException):
    status_code: int = 422
    code: str = "VALIDATION_ERROR"
    message: str = "Dữ liệu không hợp lệ. Vui lòng kiểm tra lại."


class ForbiddenAssetError(AppException):
    status_code: int = 403
    code: str = "FORBIDDEN_ASSET"
    message: str = "Bạn không có quyền truy cập ảnh này."


class IngestionNotReadyError(AppException):
    status_code: int = 409
    code: str = "INGESTION_NOT_READY"
    message: str = "Ảnh vẫn đang được xử lý. Vui lòng thử lại sau."


class ItemNotFoundError(AppException):
    status_code: int = 404
    code: str = "ITEM_NOT_FOUND"
    message: str = "Không tìm thấy món đồ này."


class ProviderError(AppException):
    status_code: int = 502
    code: str = "PROVIDER_ERROR"
    message: str = "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."
