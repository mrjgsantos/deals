from __future__ import annotations

import json

from app.ai.schemas import DealCopyOutput


def parse_copy_response(response_text: str) -> DealCopyOutput:
    payload = json.loads(response_text)
    return DealCopyOutput(
        title=str(payload["title"]).strip(),
        summary=str(payload["summary"]).strip(),
        verdict=str(payload["verdict"]).strip(),
        tags=[str(tag).strip() for tag in payload["tags"]],
    )
