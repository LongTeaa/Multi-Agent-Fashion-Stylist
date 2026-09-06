from fastapi import FastAPI

app = FastAPI(title="Multi-Agent Fashion Stylist API", version="0.1.0")


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report whether the API process is ready to accept requests."""

    return {"status": "ok"}
