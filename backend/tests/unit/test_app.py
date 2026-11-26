from fastapi.testclient import TestClient

from app.main import app


def test_health_check() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_user_facing_backend_messages_do_not_mention_ai() -> None:
    """UI copy rule: only the spec-mandated try-on labels may say "AI" (AGENTS.md section 3)."""
    import re
    from pathlib import Path

    from app.agents.context_agent import CONTEXT_FALLBACK_WARNING
    from app.schemas.common import ProviderError

    assert "AI" not in CONTEXT_FALLBACK_WARNING
    assert "AI" not in ProviderError().message
    ingestion = Path(__file__).resolve().parents[2] / "app" / "services" / "ingestion_service.py"
    warnings = re.findall(r'(?:add_warning\(|quality_warnings=\[)"([^"]+)"', ingestion.read_text(encoding="utf-8"))
    assert warnings and not [w for w in warnings if re.search(r"\bAI\b", w)]
