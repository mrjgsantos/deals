from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.client import ModelClient
from app.ai.prompt_builder import SYSTEM_PROMPT, build_copy_prompt
from app.ai.response_parser import parse_copy_response
from app.ai.schemas import StructuredDealCopyInput, ValidatedDealCopy
from app.ai.validator import validate_copy_output
from app.db.enums import AICopyDraftStatus, AICopyType
from app.db.models import AICopyDraft


class AICopyGenerationService:
    def __init__(self, client: ModelClient) -> None:
        self.client = client

    def generate_and_persist(
        self,
        db: Session,
        *,
        input_data: StructuredDealCopyInput,
        model_name: str,
        prompt_version: str,
    ) -> AICopyDraft:
        prompt = build_copy_prompt(input_data)
        response_text = self.client.generate(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
        parsed = parse_copy_response(response_text)
        validated = validate_copy_output(parsed, input_data)

        draft = AICopyDraft(
            deal_id=UUID(str(input_data.deal_id)),
            copy_type=AICopyType.PACKAGE,
            status=AICopyDraftStatus.DRAFT,
            model_name=model_name,
            prompt_version=prompt_version,
            content=_serialize_validated_copy(validated),
            metadata_json={
                "input": asdict(input_data),
                "warnings": validated.warnings,
            },
            generated_at=datetime.now(UTC),
        )
        db.add(draft)
        db.flush()
        return draft


def _serialize_validated_copy(validated: ValidatedDealCopy) -> str:
    return json.dumps(
        {
            "title": validated.output.title,
            "summary": validated.output.summary,
            "verdict": validated.output.verdict,
            "tags": validated.output.tags,
        },
        sort_keys=True,
    )
