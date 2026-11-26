from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from app.services.gemini_key_pool import GeminiKeyPool
from app.services.gemini_provider import GeminiVisionProvider


def _captured_prompt() -> str:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        body = {"attributes": {"category": "top", "formality_level": 2}, "field_confidence": {},
                "quality_warnings": []}
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]})

    provider = GeminiVisionProvider(key_pool=GeminiKeyPool([SecretStr("test-key")]),
                                    client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider.extract_attributes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    return captured["contents"][0]["parts"][0]["text"]


def test_vision_prompt_defines_every_formality_level_with_knowledge_base_anchors() -> None:
    prompt = _captured_prompt()
    formality_lines = prompt.split("- formality_level:")[1].split("- comfort_level:")[0]

    for level, anchor in [("1", "pajamas"), ("2", "crew-neck t-shirts"), ("2", "sneakers"), ("2", "street shorts"),
                          ("3", "polo shirts"), ("3", "loafers"), ("4", "long-sleeve button-up dress shirts"),
                          ("4", "blazers"), ("5", "full suits")]:
        line = next(l for l in formality_lines.splitlines() if l.strip().startswith(f"* {level}:"))
        assert anchor in line, (level, anchor)
    assert "1=very casual/loungewear" not in prompt
