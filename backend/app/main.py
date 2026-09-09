from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings, validate_vision_provider_configuration
from app.schemas.common import AppException


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Validate provider configuration before the API reports ready."""
    validate_vision_provider_configuration(get_settings())
    yield


app = FastAPI(
    title="Multi-Agent Fashion Stylist API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
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


app.include_router(api_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report whether the API process is ready to accept requests."""

    return {"status": "ok"}
