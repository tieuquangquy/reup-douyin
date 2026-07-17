from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import PublishTargetPlatform
from src.publish_routing.services.account_health_service import AccountHealthService
from src.publish_routing.services.control_queue_service import ControlQueueService
from src.publish_routing.services.draft_assignment_service import DraftAssignmentError, DraftAssignmentService
from src.publish_routing.services.routing_recommendation_service import RoutingRecommendationError, RoutingRecommendationService
from src.publish_routing.services.routing_rule_service import RoutingRuleError, RoutingRuleService
from src.schemas.publish import PublishDraftListResponse, PublishDraftResponse
from src.schemas.publish_routing import (
    AccountHealthSummaryResponse,
    BulkAssignDraftsRequest,
    DraftAssignmentRequest,
    PublishControlQueueResponse,
    PublishRoutingRuleCreateRequest,
    PublishRoutingRuleListResponse,
    PublishRoutingRuleResponse,
    PublishRoutingRuleUpdateRequest,
    RoutingRecommendationResponse,
)

router = APIRouter(tags=["publish-control"])


def get_db(db: Session = Depends(get_db_session)) -> Session:
    return db


@router.get("/publish-control/accounts", response_model=list[AccountHealthSummaryResponse])
def list_accounts_with_health(
    platform: PublishTargetPlatform = Query(default=PublishTargetPlatform.FACEBOOK_REELS),
    db: Session = Depends(get_db),
) -> list[AccountHealthSummaryResponse]:
    return AccountHealthService(db).list_account_health(platform=platform)


@router.get("/publish-control/queue", response_model=PublishControlQueueResponse)
def get_publish_control_queue(
    platform: PublishTargetPlatform = Query(default=PublishTargetPlatform.FACEBOOK_REELS),
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
) -> PublishControlQueueResponse:
    return ControlQueueService(db).queue(platform=platform, limit=limit)


@router.get("/publish-routing/recommendations", response_model=RoutingRecommendationResponse)
def get_routing_recommendation(
    publish_draft_id: UUID,
    db: Session = Depends(get_db),
) -> RoutingRecommendationResponse:
    try:
        return RoutingRecommendationService(db).recommend_for_draft(publish_draft_id)
    except RoutingRecommendationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/publish-drafts/{publish_draft_id}/assign-account", response_model=PublishDraftResponse)
def assign_publish_draft(
    publish_draft_id: UUID,
    request: DraftAssignmentRequest,
    db: Session = Depends(get_db),
) -> PublishDraftResponse:
    try:
        return PublishDraftResponse.model_validate(DraftAssignmentService(db).assign(publish_draft_id, request))
    except DraftAssignmentError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/publish-drafts/{publish_draft_id}/unassign-account", response_model=PublishDraftResponse)
def unassign_publish_draft(
    publish_draft_id: UUID,
    db: Session = Depends(get_db),
) -> PublishDraftResponse:
    try:
        return PublishDraftResponse.model_validate(DraftAssignmentService(db).unassign(publish_draft_id))
    except DraftAssignmentError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/publish-drafts/bulk-assign", response_model=PublishDraftListResponse)
def bulk_assign_publish_drafts(
    request: BulkAssignDraftsRequest,
    db: Session = Depends(get_db),
) -> PublishDraftListResponse:
    try:
        drafts = DraftAssignmentService(db).bulk_assign(request)
        return PublishDraftListResponse(drafts=[PublishDraftResponse.model_validate(draft) for draft in drafts])
    except DraftAssignmentError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/routing-rules", response_model=PublishRoutingRuleListResponse)
def list_routing_rules(
    platform: PublishTargetPlatform | None = Query(default=None),
    include_archived: bool = False,
    db: Session = Depends(get_db),
) -> PublishRoutingRuleListResponse:
    rules = RoutingRuleService(db).list_rules(platform=platform, include_archived=include_archived)
    return PublishRoutingRuleListResponse(rules=[PublishRoutingRuleResponse.model_validate(rule) for rule in rules])


@router.post("/routing-rules", response_model=PublishRoutingRuleResponse, status_code=status.HTTP_201_CREATED)
def create_routing_rule(
    request: PublishRoutingRuleCreateRequest,
    db: Session = Depends(get_db),
) -> PublishRoutingRuleResponse:
    return PublishRoutingRuleResponse.model_validate(RoutingRuleService(db).create_rule(request))


@router.patch("/routing-rules/{rule_id}", response_model=PublishRoutingRuleResponse)
def update_routing_rule(
    rule_id: UUID,
    request: PublishRoutingRuleUpdateRequest,
    db: Session = Depends(get_db),
) -> PublishRoutingRuleResponse:
    try:
        return PublishRoutingRuleResponse.model_validate(RoutingRuleService(db).update_rule(rule_id, request))
    except RoutingRuleError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

