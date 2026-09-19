import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.v1.router import api_router
from app.core.config import (
    get_settings,
    validate_image_provider_configuration,
    validate_vision_provider_configuration,
)
from app.repositories.object_storage import ObjectNotFoundError, ObjectStorageError
from app.schemas.common import AppException

from app.services.cleanup_scheduler import start_cleanup_scheduler, stop_cleanup_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Validate provider configuration and manage operational background tasks."""
    settings = get_settings()
    validate_vision_provider_configuration(settings)
    validate_image_provider_configuration(settings)

    if settings.cleanup_scheduler_enabled:
        start_cleanup_scheduler(interval_seconds=settings.cleanup_interval_seconds)

    try:
        yield
    finally:
        if settings.cleanup_scheduler_enabled:
            await stop_cleanup_scheduler()


app = FastAPI(
    title="Multi-Agent Fashion Stylist API",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
cors_origins = list(settings.cors_origins)
frontend_url_str = str(settings.frontend_url).rstrip("/")
if frontend_url_str and frontend_url_str not in cors_origins:
    cors_origins.append(frontend_url_str)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.",
                "details": jsonable_encoder(
                    exc.errors(), custom_encoder={ValueError: str}
                ),
            },
        },
    )


@app.exception_handler(ObjectNotFoundError)
async def handle_object_not_found(_: Request, exc: ObjectNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "success": False,
            "error": {
                "code": "OBJECT_NOT_FOUND",
                "message": "Không tìm thấy tệp phương tiện yêu cầu trên hệ thống lưu trữ.",
                "details": None,
            },
        },
    )


@app.exception_handler(ObjectStorageError)
async def handle_object_storage_error(_: Request, exc: ObjectStorageError) -> JSONResponse:
    logger.error("Object storage error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "success": False,
            "error": {
                "code": "STORAGE_ERROR",
                "message": "Hệ thống lưu trữ tệp tạm thời gặp sự cố. Vui lòng thử lại sau.",
                "details": None,
            },
        },
    )


@app.exception_handler(IntegrityError)
async def handle_integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Database integrity conflict: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "success": False,
            "error": {
                "code": "DATA_CONFLICT",
                "message": "Dữ liệu bị xung đột hoặc đã tồn tại trên hệ thống.",
                "details": None,
            },
        },
    )


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("Database error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "DATABASE_ERROR",
                "message": "Đã xảy ra lỗi cơ sở dữ liệu. Vui lòng thử lại sau.",
                "details": None,
            },
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("X-Request-Id") or str(uuid4())
    logger.exception(
        "Unhandled exception [request_id=%s] on %s %s: %s",
        request_id,
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Đã xảy ra lỗi hệ thống không mong muốn. Vui lòng thử lại sau.",
                "details": {"request_id": request_id},
            },
        },
    )


app.include_router(api_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report whether the API process is ready to accept requests."""

    return {"status": "ok"}
