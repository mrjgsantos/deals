from __future__ import annotations

import json
import re
import unicodedata

from app.ai.schemas import DealCopyOutput

_TAG_INVALID_RE = re.compile(r"[^a-z0-9-]")


def _normalize_tag(raw: str) -> str | None:
    """Normalize a model-generated tag to [a-z0-9-]{2,24}.

    Strips accents, lowercases, replaces spaces/underscores with hyphens,
    removes remaining invalid chars, and truncates. Returns None if the
    result is too short to be useful.
    """
    tag = unicodedata.normalize("NFD", raw.strip().lower())
    tag = "".join(c for c in tag if unicodedata.category(c) != "Mn")
    tag = tag.replace(" ", "-").replace("_", "-")
    tag = _TAG_INVALID_RE.sub("", tag)
    tag = re.sub(r"-{2,}", "-", tag).strip("-")[:24]
    return tag if len(tag) >= 2 else None


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
        tags=[n for tag in payload["tags"] if (n := _normalize_tag(str(tag))) is not None],
    )
