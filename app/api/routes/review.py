from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_deal_query_service, get_review_service
from app.db.session import get_db
from app.schemas.api import ReviewDecisionResponse, ReviewQueueItemResponse
from app.services.deal_service import DealQueryService, ReviewQueueRecord
from app.services.review_service import ReviewService

router = APIRouter(prefix="/review")


@router.get("/pending", response_model=list[ReviewQueueItemResponse])
def get_pending_review(
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> list[ReviewQueueItemResponse]:
    review_items = service.list_pending_review_items(db)
    return [ReviewQueueItemResponse.model_validate(item) for item in review_items]


@router.post("/{review_id}/approve", response_model=ReviewDecisionResponse)
def approve_deal(
    review_id: UUID,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
) -> ReviewDecisionResponse:
    try:
        decision = service.approve(db, review_id)
    except ValueError as exc:
        if str(exc) == "review_not_found":
            raise HTTPException(status_code=404, detail="review_not_found") from None
        if str(exc) == "deal_not_found":
            raise HTTPException(status_code=404, detail="deal_not_found") from None
        if str(exc) in {"review_already_resolved", "invalid_deal_state", "unsupported_review_type"}:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return ReviewDecisionResponse(
        review_id=decision.review_id,
        review_status=decision.review_status,
        deal_id=decision.deal_id,
        deal_status=decision.deal_status,
    )


@router.post("/{review_id}/reject", response_model=ReviewDecisionResponse)
def reject_deal(
    review_id: UUID,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
) -> ReviewDecisionResponse:
    try:
        decision = service.reject(db, review_id)
    except ValueError as exc:
        if str(exc) == "review_not_found":
            raise HTTPException(status_code=404, detail="review_not_found") from None
        if str(exc) == "deal_not_found":
            raise HTTPException(status_code=404, detail="deal_not_found") from None
        if str(exc) in {"review_already_resolved", "invalid_deal_state", "unsupported_review_type"}:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return ReviewDecisionResponse(
        review_id=decision.review_id,
        review_status=decision.review_status,
        deal_id=decision.deal_id,
        deal_status=decision.deal_status,
    )
