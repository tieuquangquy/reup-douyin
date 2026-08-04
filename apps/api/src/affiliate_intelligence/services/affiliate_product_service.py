from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import logging
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.content_intelligence.services.content_classification_service import normalize_for_matching
from src.enums import JobType
from src.models.affiliate import AffiliateProduct, AffiliateProductMatch, AffiliateProductTopicMapping
from src.models.content_intelligence import ContentClassification, TopicCategory
from src.models.jobs import Job
from src.models.publish import PlatformAccount, PlatformPublication
from src.schemas.affiliate import (
    AffiliateProductCreateRequest,
    AffiliateProductMatchDecisionRequest,
    AffiliateProductMatchRunRequest,
    AffiliateProductUpdateRequest,
)
from src.services.job_service import JobService


logger = logging.getLogger(__name__)

DEFAULT_CATALOG_VERSION = "AFFILIATE_CATALOG_V1"
DEFAULT_MATCHER_VERSION = "AFFILIATE_MATCHER_V1"


class AffiliateIntelligenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def product_identity_fingerprint(*, platform: str, external_product_id: str | None, affiliate_url: str) -> str:
    identity = f"{platform.strip().upper()}:{(external_product_id or '').strip() or affiliate_url.strip()}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class AffiliateCatalogService:
    def __init__(self, db: Session):
        self.db = db

    def list_products(
        self,
        workspace_id: UUID,
        *,
        query: str | None = None,
        platform: str | None = None,
        availability_status: str | None = None,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AffiliateProduct], int, int, int]:
        filters = [AffiliateProduct.workspace_id == workspace_id]
        if platform:
            filters.append(AffiliateProduct.platform == platform)
        if availability_status:
            filters.append(AffiliateProduct.availability_status == availability_status)
        if active_only:
            filters.append(AffiliateProduct.is_active.is_(True))
        cleaned = (query or "").strip()
        if cleaned:
            pattern = f"%{cleaned}%"
            filters.append(
                or_(
                    AffiliateProduct.name.ilike(pattern),
                    AffiliateProduct.merchant_name.ilike(pattern),
                    AffiliateProduct.external_product_id.ilike(pattern),
                )
            )
        products = list(
            self.db.scalars(
                select(AffiliateProduct)
                .options(selectinload(AffiliateProduct.topic_mappings))
                .where(*filters)
                .order_by(AffiliateProduct.is_active.desc(), AffiliateProduct.updated_at.desc())
                .limit(limit)
                .offset(offset)
            ).unique()
        )
        total = int(self.db.scalar(select(func.count()).select_from(AffiliateProduct).where(*filters)) or 0)
        active_count = int(
            self.db.scalar(
                select(func.count()).select_from(AffiliateProduct).where(
                    AffiliateProduct.workspace_id == workspace_id,
                    AffiliateProduct.is_active.is_(True),
                )
            )
            or 0
        )
        out_of_stock_count = int(
            self.db.scalar(
                select(func.count()).select_from(AffiliateProduct).where(
                    AffiliateProduct.workspace_id == workspace_id,
                    AffiliateProduct.availability_status == "OUT_OF_STOCK",
                )
            )
            or 0
        )
        return products, total, active_count, out_of_stock_count

    def create(self, workspace_id: UUID, request: AffiliateProductCreateRequest) -> AffiliateProduct:
        fingerprint = product_identity_fingerprint(
            platform=request.platform,
            external_product_id=request.external_product_id,
            affiliate_url=request.affiliate_url,
        )
        if self.db.scalar(
            select(AffiliateProduct.id).where(
                AffiliateProduct.workspace_id == workspace_id,
                AffiliateProduct.fingerprint_sha256 == fingerprint,
            )
        ):
            raise AffiliateIntelligenceError("affiliate_product_exists", "This affiliate product is already in the catalog")
        product = AffiliateProduct(
            workspace_id=workspace_id,
            fingerprint_sha256=fingerprint,
            metadata_json={"source": "OPERATOR"},
        )
        self._apply(product, workspace_id, request.model_dump(), creating=True)
        self.db.add(product)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AffiliateIntelligenceError("affiliate_product_exists", "This affiliate product is already in the catalog") from exc
        return self.get(workspace_id, product.id)

    def update(
        self,
        workspace_id: UUID,
        product_id: UUID,
        request: AffiliateProductUpdateRequest,
    ) -> AffiliateProduct:
        product = self.get(workspace_id, product_id)
        payload = request.model_dump(exclude_unset=True)
        self._apply(product, workspace_id, payload, creating=False)
        duplicate = self.db.scalar(
            select(AffiliateProduct.id).where(
                AffiliateProduct.workspace_id == workspace_id,
                AffiliateProduct.fingerprint_sha256 == product.fingerprint_sha256,
                AffiliateProduct.id != product.id,
            )
        )
        if duplicate is not None:
            self.db.rollback()
            raise AffiliateIntelligenceError("affiliate_product_exists", "This affiliate product is already in the catalog")
        self.db.commit()
        return self.get(workspace_id, product.id)

    def bulk_import(
        self,
        workspace_id: UUID,
        requests: list[AffiliateProductCreateRequest],
    ) -> tuple[list[AffiliateProduct], int, int, int]:
        result_ids: list[UUID] = []
        created = 0
        updated_count = 0
        skipped = 0
        for request in requests:
            fingerprint = product_identity_fingerprint(
                platform=request.platform,
                external_product_id=request.external_product_id,
                affiliate_url=request.affiliate_url,
            )
            product = self.db.scalar(
                select(AffiliateProduct).where(
                    AffiliateProduct.workspace_id == workspace_id,
                    AffiliateProduct.fingerprint_sha256 == fingerprint,
                )
            )
            if product is None:
                product = AffiliateProduct(
                    workspace_id=workspace_id,
                    fingerprint_sha256=fingerprint,
                    metadata_json={"source": "CSV_IMPORT"},
                )
                self.db.add(product)
                self._apply(product, workspace_id, request.model_dump(), creating=True)
                created += 1
            else:
                before = self._business_snapshot(product)
                self._apply(product, workspace_id, request.model_dump(), creating=False)
                if before == self._business_snapshot(product):
                    skipped += 1
                else:
                    updated_count += 1
            self.db.flush()
            result_ids.append(product.id)
        self.db.commit()
        products = [self.get(workspace_id, product_id) for product_id in result_ids]
        logger.info(
            "affiliate_catalog_bulk_imported",
            extra={
                "workspace_id": str(workspace_id),
                "created_count": created,
                "updated_count": updated_count,
                "skipped_count": skipped,
            },
        )
        return products, created, updated_count, skipped

    def get(self, workspace_id: UUID, product_id: UUID) -> AffiliateProduct:
        product = self.db.scalar(
            select(AffiliateProduct)
            .options(selectinload(AffiliateProduct.topic_mappings))
            .where(AffiliateProduct.id == product_id, AffiliateProduct.workspace_id == workspace_id)
        )
        if product is None:
            raise AffiliateIntelligenceError("affiliate_product_not_found", "Affiliate product was not found")
        return product

    def topic_details(self, product: AffiliateProduct) -> tuple[list[UUID], list[str], list[str]]:
        ids = [mapping.topic_category_id for mapping in product.topic_mappings]
        topics = [self.db.get(TopicCategory, topic_id) for topic_id in ids]
        valid = [topic for topic in topics if topic is not None]
        return ids, [topic.code for topic in valid], [topic.name for topic in valid]

    def catalog_fingerprint(self, workspace_id: UUID, catalog_version: str = DEFAULT_CATALOG_VERSION) -> str:
        products = list(
            self.db.scalars(
                select(AffiliateProduct)
                .options(selectinload(AffiliateProduct.topic_mappings))
                .where(
                    AffiliateProduct.workspace_id == workspace_id,
                    AffiliateProduct.catalog_version == catalog_version,
                    AffiliateProduct.is_active.is_(True),
                    AffiliateProduct.availability_status != "OUT_OF_STOCK",
                )
                .order_by(AffiliateProduct.id.asc())
            ).unique()
        )
        payload = [
            {
                "id": str(product.id),
                "fingerprint": product.fingerprint_sha256,
                "updated_at": product.updated_at.isoformat() if product.updated_at else None,
                "availability": product.availability_status,
                "topics": sorted(str(mapping.topic_category_id) for mapping in product.topic_mappings),
            }
            for product in products
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _apply(self, product: AffiliateProduct, workspace_id: UUID, payload: dict, *, creating: bool) -> None:
        fields = (
            "catalog_version",
            "platform",
            "external_product_id",
            "merchant_name",
            "name",
            "description",
            "image_url",
            "product_url",
            "affiliate_url",
            "currency_code",
            "price_amount",
            "commission_rate_percent",
            "commission_amount",
            "availability_status",
            "is_active",
        )
        for field in fields:
            if field in payload:
                value = payload[field]
                if isinstance(value, str):
                    value = value.strip()
                setattr(product, field, value)
        if creating:
            product.catalog_version = str(payload.get("catalog_version") or DEFAULT_CATALOG_VERSION)
        if "keywords" in payload:
            product.keywords_json = list(payload.get("keywords") or [])
        if "supported_platforms" in payload:
            product.supported_platforms_json = list(payload.get("supported_platforms") or [])
        if "topic_ids" in payload:
            topic_ids = list(dict.fromkeys(payload.get("topic_ids") or []))
            topics = list(
                self.db.scalars(
                    select(TopicCategory).where(
                        TopicCategory.workspace_id == workspace_id,
                        TopicCategory.id.in_(topic_ids),
                        TopicCategory.is_active.is_(True),
                    )
                )
            ) if topic_ids else []
            if len(topics) != len(topic_ids):
                raise AffiliateIntelligenceError(
                    "affiliate_topic_invalid", "Every product topic must exist and be active in this workspace"
                )
            product.topic_mappings.clear()
            for topic_id in topic_ids:
                product.topic_mappings.append(
                    AffiliateProductTopicMapping(
                        workspace_id=workspace_id,
                        topic_category_id=topic_id,
                        relevance_weight=1.0,
                        source="OPERATOR" if (product.metadata_json or {}).get("source") == "OPERATOR" else "CSV_IMPORT",
                    )
                )
        if not str(product.name or "").strip() or not str(product.affiliate_url or "").strip():
            raise AffiliateIntelligenceError(
                "affiliate_product_fields_required", "Product name and affiliate URL are required"
            )
        product.fingerprint_sha256 = product_identity_fingerprint(
            platform=product.platform,
            external_product_id=product.external_product_id,
            affiliate_url=product.affiliate_url,
        )

    @staticmethod
    def _business_snapshot(product: AffiliateProduct) -> tuple:
        return (
            product.platform,
            product.external_product_id,
            product.merchant_name,
            product.name,
            product.description,
            product.image_url,
            product.product_url,
            product.affiliate_url,
            product.currency_code,
            product.price_amount,
            product.commission_rate_percent,
            product.commission_amount,
            product.availability_status,
            tuple(product.keywords_json or []),
            tuple(product.supported_platforms_json or []),
            tuple(sorted(str(item.topic_category_id) for item in product.topic_mappings)),
            product.is_active,
        )


class AffiliateProductMatchingService:
    def __init__(self, db: Session):
        self.db = db
        self.catalog = AffiliateCatalogService(db)

    def enqueue(
        self,
        publication_id: UUID,
        workspace_id: UUID,
        request: AffiliateProductMatchRunRequest,
    ) -> tuple[AffiliateProductMatch | None, Job | None, bool]:
        publication, classification = self._eligible_publication(publication_id, workspace_id)
        catalog_fingerprint = self.catalog.catalog_fingerprint(workspace_id)
        if catalog_fingerprint == self._empty_catalog_fingerprint():
            raise AffiliateIntelligenceError(
                "affiliate_catalog_empty", "Add at least one active, available product before running product matching"
            )
        existing = self.db.scalar(
            select(AffiliateProductMatch).where(
                AffiliateProductMatch.platform_publication_id == publication.id,
                AffiliateProductMatch.content_classification_id == classification.id,
                AffiliateProductMatch.matcher_version == request.matcher_version,
                AffiliateProductMatch.catalog_fingerprint_sha256 == catalog_fingerprint,
            )
        )
        if existing is not None:
            self._make_current(existing)
            self.db.commit()
            return existing, None, True
        idempotency_key = (
            f"affiliate-product-match:{publication.id}:{classification.id}:"
            f"{request.matcher_version}:{catalog_fingerprint[:20]}"
        )
        existing_job = self.db.scalar(
            select(Job).where(Job.workspace_id == workspace_id, Job.idempotency_key == idempotency_key)
        )
        if existing_job is not None:
            return None, JobService(self.db).get_job(existing_job.id), True
        job = JobService(self.db).create_job(
            workspace_id=workspace_id,
            job_type=JobType.MATCH_AFFILIATE_PRODUCTS,
            source_video_id=publication.source_video_id,
            reference_type="platform_publication_affiliate_product_match",
            reference_id=publication.id,
            idempotency_key=idempotency_key,
            max_attempts=2,
            payload_json={
                "platform_publication_id": str(publication.id),
                "content_classification_id": str(classification.id),
                "matcher_version": request.matcher_version,
                "catalog_version": DEFAULT_CATALOG_VERSION,
                "catalog_fingerprint_sha256": catalog_fingerprint,
                "max_suggestions": request.max_suggestions,
            },
        )
        logger.info(
            "affiliate_product_match_job_created",
            extra={"workspace_id": str(workspace_id), "publication_id": str(publication.id), "job_id": str(job.id)},
        )
        return None, job, False

    def execute_job(self, job_id: UUID) -> AffiliateProductMatch:
        job = JobService(self.db).get_job(job_id)
        if job.job_type != JobType.MATCH_AFFILIATE_PRODUCTS:
            raise AffiliateIntelligenceError("affiliate_match_job_type_invalid", "Job is not a product matching job")
        payload = job.payload_json or {}
        try:
            publication_id = UUID(str(payload["platform_publication_id"]))
            classification_id = UUID(str(payload["content_classification_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AffiliateIntelligenceError("affiliate_match_input_missing", "Product matching job input is incomplete") from exc
        publication, classification = self._eligible_publication(publication_id, job.workspace_id)
        if classification.id != classification_id:
            raise AffiliateIntelligenceError(
                "affiliate_classification_changed",
                "The approved classification changed; enqueue product matching again",
            )
        matcher_version = str(payload.get("matcher_version") or DEFAULT_MATCHER_VERSION)
        catalog_version = str(payload.get("catalog_version") or DEFAULT_CATALOG_VERSION)
        catalog_fingerprint = self.catalog.catalog_fingerprint(job.workspace_id, catalog_version)
        if catalog_fingerprint != str(payload.get("catalog_fingerprint_sha256") or ""):
            raise AffiliateIntelligenceError(
                "affiliate_catalog_changed", "The affiliate catalog changed; enqueue product matching again"
            )
        existing = self.db.scalar(
            select(AffiliateProductMatch).where(
                AffiliateProductMatch.platform_publication_id == publication.id,
                AffiliateProductMatch.content_classification_id == classification.id,
                AffiliateProductMatch.matcher_version == matcher_version,
                AffiliateProductMatch.catalog_fingerprint_sha256 == catalog_fingerprint,
            )
        )
        if existing is not None:
            self._make_current(existing)
            job.result_json = {"affiliate_product_match_id": str(existing.id), "reused": True}
            self.db.commit()
            return existing
        products = list(
            self.db.scalars(
                select(AffiliateProduct)
                .options(selectinload(AffiliateProduct.topic_mappings))
                .where(
                    AffiliateProduct.workspace_id == job.workspace_id,
                    AffiliateProduct.catalog_version == catalog_version,
                    AffiliateProduct.is_active.is_(True),
                    AffiliateProduct.availability_status != "OUT_OF_STOCK",
                )
            ).unique()
        )
        suggestions = self._match(
            publication=publication,
            classification=classification,
            products=products,
            max_suggestions=max(1, min(int(payload.get("max_suggestions") or 5), 10)),
        )
        self.db.execute(
            update(AffiliateProductMatch)
            .where(
                AffiliateProductMatch.platform_publication_id == publication.id,
                AffiliateProductMatch.is_current.is_(True),
            )
            .values(is_current=False)
        )
        product_match = AffiliateProductMatch(
            workspace_id=job.workspace_id,
            platform_publication_id=publication.id,
            content_classification_id=classification.id,
            matcher_version=matcher_version,
            catalog_version=catalog_version,
            catalog_fingerprint_sha256=catalog_fingerprint,
            decision_status="NEEDS_REVIEW",
            suggestions_json=suggestions,
            selected_product_id=None,
            selected_fit_score=None,
            created_by_job_id=job.id,
            is_current=True,
            metadata_json={
                "score_version": "AFFILIATE_FIT_SCORE_V1",
                "candidate_product_count": len(products),
                "suggestion_count": len(suggestions),
                "auto_placement": False,
            },
        )
        self.db.add(product_match)
        self.db.flush()
        job.result_json = {
            "affiliate_product_match_id": str(product_match.id),
            "suggestion_count": len(suggestions),
            "top_affiliate_fit_score": suggestions[0]["affiliate_fit_score"] if suggestions else None,
        }
        self.db.commit()
        self.db.refresh(product_match)
        logger.info(
            "affiliate_product_match_completed",
            extra={
                "workspace_id": str(job.workspace_id),
                "publication_id": str(publication.id),
                "product_match_id": str(product_match.id),
                "suggestion_count": len(suggestions),
            },
        )
        return product_match

    def get_current(self, publication_id: UUID, workspace_id: UUID) -> AffiliateProductMatch | None:
        self._publication(publication_id, workspace_id)
        return self.db.scalar(
            select(AffiliateProductMatch).where(
                AffiliateProductMatch.workspace_id == workspace_id,
                AffiliateProductMatch.platform_publication_id == publication_id,
                AffiliateProductMatch.is_current.is_(True),
            )
        )

    def decide(
        self,
        match_id: UUID,
        workspace_id: UUID,
        operator_subject: str,
        request: AffiliateProductMatchDecisionRequest,
    ) -> AffiliateProductMatch:
        product_match = self.db.get(AffiliateProductMatch, match_id)
        if product_match is None or product_match.workspace_id != workspace_id or not product_match.is_current:
            raise AffiliateIntelligenceError("affiliate_product_match_not_found", "Current product match was not found")
        selected_product = None
        if request.selected_product_id is not None:
            selected_product = self.catalog.get(workspace_id, request.selected_product_id)
            if not selected_product.is_active or selected_product.availability_status == "OUT_OF_STOCK":
                raise AffiliateIntelligenceError(
                    "affiliate_product_unavailable", "Selected affiliate product is inactive or out of stock"
                )
        suggestions = list(product_match.suggestions_json or [])
        suggestion = next(
            (item for item in suggestions if str(item.get("product_id")) == str(request.selected_product_id)),
            None,
        )
        if request.decision == "APPROVED" and suggestion is None:
            raise AffiliateIntelligenceError(
                "affiliate_product_not_suggested", "Approve one of the suggested products or use Override"
            )
        product_match.decision_status = request.decision
        product_match.selected_product_id = selected_product.id if selected_product else None
        product_match.selected_fit_score = float(suggestion["affiliate_fit_score"]) if suggestion else None
        product_match.reviewed_by = operator_subject[:180]
        product_match.reviewed_at = datetime.now(UTC)
        product_match.decision_reason = (request.reason or "").strip() or None
        product_match.metadata_json = {
            **(product_match.metadata_json or {}),
            "operator_reviewed": True,
            "placement_authorized": False,
        }
        self.db.commit()
        self.db.refresh(product_match)
        logger.info(
            "affiliate_product_match_decided",
            extra={
                "workspace_id": str(workspace_id),
                "product_match_id": str(product_match.id),
                "decision": product_match.decision_status,
                "selected_product_id": str(product_match.selected_product_id) if product_match.selected_product_id else None,
            },
        )
        return product_match

    def review_queue(
        self,
        workspace_id: UUID,
        *,
        decision_status: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[tuple[PlatformPublication, PlatformAccount, ContentClassification, AffiliateProductMatch | None]], int, dict, dict[UUID, Job]]:
        classification_join = and_(
            ContentClassification.platform_publication_id == PlatformPublication.id,
            ContentClassification.workspace_id == workspace_id,
            ContentClassification.is_current.is_(True),
            ContentClassification.decision_status.in_(["APPROVED", "OVERRIDDEN"]),
        )
        match_join = and_(
            AffiliateProductMatch.platform_publication_id == PlatformPublication.id,
            AffiliateProductMatch.is_current.is_(True),
        )
        filters = [PlatformPublication.workspace_id == workspace_id]
        if decision_status == "UNMATCHED":
            filters.append(AffiliateProductMatch.id.is_(None))
        elif decision_status:
            filters.append(AffiliateProductMatch.decision_status == decision_status)
        cleaned = (query or "").strip()
        if cleaned:
            pattern = f"%{cleaned}%"
            filters.append(
                or_(
                    PlatformPublication.external_reel_id.ilike(pattern),
                    PlatformAccount.display_name.ilike(pattern),
                    ContentClassification.primary_topic_code.ilike(pattern),
                )
            )
        base = (
            select(PlatformPublication, PlatformAccount, ContentClassification, AffiliateProductMatch)
            .join(PlatformAccount, PlatformAccount.id == PlatformPublication.platform_account_id)
            .join(ContentClassification, classification_join)
            .outerjoin(AffiliateProductMatch, match_join)
            .where(*filters)
        )
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = list(
            self.db.execute(
                base.order_by(
                    AffiliateProductMatch.decision_status.asc().nullsfirst(),
                    PlatformPublication.published_at.desc().nullslast(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
        )
        publication_ids = [row[0].id for row in rows]
        latest_jobs: dict[UUID, Job] = {}
        if publication_ids:
            for job in self.db.scalars(
                select(Job)
                .where(
                    Job.workspace_id == workspace_id,
                    Job.reference_type == "platform_publication_affiliate_product_match",
                    Job.reference_id.in_(publication_ids),
                )
                .order_by(Job.created_at.desc())
            ):
                if job.reference_id and job.reference_id not in latest_jobs:
                    latest_jobs[job.reference_id] = job
        catalog_fingerprint = self.catalog.catalog_fingerprint(workspace_id)
        eligible_count = int(
            self.db.scalar(
                select(func.count()).select_from(PlatformPublication).join(ContentClassification, classification_join).where(
                    PlatformPublication.workspace_id == workspace_id
                )
            )
            or 0
        )
        status_counts = {
            str(status): int(count)
            for status, count in self.db.execute(
                select(AffiliateProductMatch.decision_status, func.count())
                .where(AffiliateProductMatch.workspace_id == workspace_id, AffiliateProductMatch.is_current.is_(True))
                .group_by(AffiliateProductMatch.decision_status)
            ).all()
        }
        current_match_count = sum(status_counts.values())
        stale_count = int(
            self.db.scalar(
                select(func.count()).select_from(AffiliateProductMatch).where(
                    AffiliateProductMatch.workspace_id == workspace_id,
                    AffiliateProductMatch.is_current.is_(True),
                    AffiliateProductMatch.catalog_fingerprint_sha256 != catalog_fingerprint,
                )
            )
            or 0
        )
        kpis = {
            "eligible_publications": eligible_count,
            "unmatched_count": max(0, eligible_count - current_match_count),
            "needs_review_count": status_counts.get("NEEDS_REVIEW", 0),
            "approved_count": status_counts.get("APPROVED", 0),
            "rejected_count": status_counts.get("REJECTED", 0),
            "stale_count": stale_count,
        }
        return rows, total, kpis, latest_jobs

    def _match(
        self,
        *,
        publication: PlatformPublication,
        classification: ContentClassification,
        products: list[AffiliateProduct],
        max_suggestions: int,
    ) -> list[dict]:
        evidence_text = " ".join(
            str(item.get("text") or "") for item in (classification.evidence_json or []) if isinstance(item, dict)
        )
        normalized_evidence = normalize_for_matching(evidence_text)
        primary_topic_id = classification.primary_topic_id
        secondary_ids = {
            str(item.get("topic_id"))
            for item in (classification.secondary_topics_json or [])
            if isinstance(item, dict) and item.get("topic_id")
        }
        publication_platform = str(publication.platform)
        scored: list[dict] = []
        for product in products:
            mapped_ids = {mapping.topic_category_id for mapping in product.topic_mappings}
            topic_score = 0.0
            evidence: list[str] = []
            if primary_topic_id in mapped_ids:
                topic_score = 40.0
                evidence.append(f"primary_topic:{classification.primary_topic_code}")
            elif any(str(topic_id) in secondary_ids for topic_id in mapped_ids):
                topic_score = 24.0
                evidence.append("secondary_topic_match")

            raw_keywords = [*(product.keywords_json or [])]
            matched_keywords: list[str] = []
            for raw_keyword in raw_keywords:
                keyword = normalize_for_matching(str(raw_keyword))
                if keyword and keyword in normalized_evidence:
                    matched_keywords.append(str(raw_keyword))
            keyword_score = min(25.0, len(set(item.casefold() for item in matched_keywords)) * 6.25)
            evidence.extend(f"keyword:{keyword}" for keyword in matched_keywords[:5])

            # Availability and commission can rank relevant products, but must never
            # make an unrelated product eligible on their own.
            if topic_score <= 0 and keyword_score <= 0:
                continue

            availability_score = 15.0 if product.availability_status == "IN_STOCK" else 6.0
            commission = float(product.commission_rate_percent or 0.0)
            commission_score = 10.0 if commission >= 20 else 7.0 if commission >= 10 else 4.0 if commission > 0 else 0.0
            supported = {str(value) for value in product.supported_platforms_json or []}
            platform_score = 10.0 if publication_platform in supported else 0.0
            total = round(topic_score + keyword_score + availability_score + commission_score + platform_score, 2)
            if total <= 0:
                continue
            scored.append(
                {
                    "rank": 0,
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "merchant_name": product.merchant_name,
                    "platform": product.platform,
                    "affiliate_url": product.affiliate_url,
                    "image_url": product.image_url,
                    "price_amount": product.price_amount,
                    "currency_code": product.currency_code,
                    "commission_rate_percent": product.commission_rate_percent,
                    "availability_status": product.availability_status,
                    "affiliate_fit_score": total,
                    "score_breakdown": {
                        "topic_relevance": topic_score,
                        "keyword_entity_match": keyword_score,
                        "availability": availability_score,
                        "commission_quality": commission_score,
                        "platform_compatibility": platform_score,
                    },
                    "evidence": evidence[:8],
                }
            )
        scored.sort(key=lambda item: (-item["affiliate_fit_score"], item["product_name"].casefold()))
        for index, item in enumerate(scored[:max_suggestions], start=1):
            item["rank"] = index
        return scored[:max_suggestions]

    def _eligible_publication(
        self,
        publication_id: UUID,
        workspace_id: UUID,
    ) -> tuple[PlatformPublication, ContentClassification]:
        publication = self._publication(publication_id, workspace_id)
        classification = self.db.scalar(
            select(ContentClassification).where(
                ContentClassification.workspace_id == workspace_id,
                ContentClassification.platform_publication_id == publication.id,
                ContentClassification.is_current.is_(True),
            )
        )
        if classification is None:
            raise AffiliateIntelligenceError(
                "affiliate_classification_missing", "Classify and approve this publication before product matching"
            )
        if classification.decision_status not in {"APPROVED", "OVERRIDDEN"}:
            raise AffiliateIntelligenceError(
                "affiliate_classification_not_approved",
                "Approve or override the topic classification before product matching",
            )
        return publication, classification

    def _publication(self, publication_id: UUID, workspace_id: UUID) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, publication_id)
        if publication is None or publication.workspace_id != workspace_id:
            raise AffiliateIntelligenceError("affiliate_publication_not_found", "Platform publication was not found")
        return publication

    def _make_current(self, product_match: AffiliateProductMatch) -> None:
        self.db.execute(
            update(AffiliateProductMatch)
            .where(
                AffiliateProductMatch.platform_publication_id == product_match.platform_publication_id,
                AffiliateProductMatch.id != product_match.id,
                AffiliateProductMatch.is_current.is_(True),
            )
            .values(is_current=False)
        )
        product_match.is_current = True

    @staticmethod
    def _empty_catalog_fingerprint() -> str:
        return hashlib.sha256(b"[]").hexdigest()
