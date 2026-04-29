from __future__ import annotations

import json

from app.ai.schemas import DealCopyOutput


def parse_copy_response(response_text: str) -> DealCopyOutput:
    text = (response_text or "").strip()
    # Strip markdown code fences that some models add
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    if not text:
        raise ValueError("empty response from model")
    payload = json.loads(text)
    return DealCopyOutput(
        title=str(payload["title"]).strip(),
        title_pt=str(payload["title_pt"]).strip(),
        summary=str(payload["summary"]).strip(),
        verdict=str(payload["verdict"]).strip(),
        tags=[str(tag).strip() for tag in payload["tags"]],
    )
