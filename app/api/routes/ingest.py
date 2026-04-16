from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_ingestion_service, get_staff_user
from app.db.session import get_db
from app.ingestion.exceptions import PayloadValidationError, SourceNotFoundError
from app.schemas.api import IngestRunRequest, IngestRunResponse

router = APIRouter(prefix="/ingest", dependencies=[Depends(get_staff_user)])
logger = logging.getLogger(__name__)


@router.post("/run", response_model=IngestRunResponse)
def run_ingestion(
    request: IngestRunRequest,
    db: Session = Depends(get_db),
) -> IngestRunResponse:
    try:
        service = get_ingestion_service(request.parser)
    except KeyError:
        raise HTTPException(status_code=400, detail="unsupported_parser") from None

    try:
        result = service.ingest(db, source_slug=request.source_slug, payload=request.payload)
        db.commit()
    except SourceNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="source_not_found") from None
    except PayloadValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception:
        db.rollback()
        logger.exception(
            "ingest_run_failed source=%s parser=%s",
            request.source_slug,
            request.parser,
        )
        raise HTTPException(status_code=500, detail="ingestion_failed") from None

    return IngestRunResponse.model_validate(result.model_dump(mode="json"))
