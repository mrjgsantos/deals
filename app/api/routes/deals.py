from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_deal_publication_service, get_deal_query_service
from app.db.enums import DealStatus
from app.db.session import get_db
from app.schemas.api import DealPublicationResponse, DealResponse
from app.services.deal_service import DealPublicationService, DealQueryService

router = APIRouter(prefix="/deals")


@router.get("", response_model=list[DealResponse])
def list_deals(
    status: DealStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> list[DealResponse]:
    deals = service.list_deals(db, status=status)
    return [DealResponse.model_validate(deal) for deal in deals]


@router.get("/{deal_id}", response_model=DealResponse)
def get_deal(
    deal_id: UUID,
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> DealResponse:
    deal = service.get_deal(db, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="deal_not_found")
    return DealResponse.model_validate(deal)


@router.post("/{deal_id}/publish", response_model=DealPublicationResponse)
def publish_deal(
    deal_id: UUID,
    db: Session = Depends(get_db),
    service: DealPublicationService = Depends(get_deal_publication_service),
) -> DealPublicationResponse:
    try:
        result = service.mark_published(db, deal_id)
    except ValueError as exc:
        detail = str(exc)
        if detail == "deal_not_found":
            raise HTTPException(status_code=404, detail=detail) from exc
        if detail == "invalid_deal_state":
            raise HTTPException(status_code=409, detail=detail) from exc
        raise
    return DealPublicationResponse(
        deal_id=result.deal_id,
        deal_status=result.deal_status,
        published_at=result.published_at,
    )
