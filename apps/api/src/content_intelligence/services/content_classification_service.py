from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import logging
import re
import unicodedata
from uuid import UUID

from sqlalchemy import String, and_, cast, distinct, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.enums import JobType, OcrObjectStatus, TranscriptSegmentStatus
from src.models.artifacts import OcrTextObject, TranscriptSegment
from src.models.content_intelligence import ContentClassification, TopicCategory
from src.models.ingestion import SourceVideo
from src.models.jobs import Job
from src.models.publish import PlatformAccount, PlatformPublication, PublishDraft
from src.content_intelligence.services.content_ai_settings_service import ContentAiSettingsService
from src.schemas.content_intelligence import (
    ContentClassificationDecisionRequest,
    ContentClassificationRunRequest,
    TopicCategoryCreateRequest,
    TopicCategoryUpdateRequest,
)
from src.services.job_service import JobService


logger = logging.getLogger(__name__)

DEFAULT_TAXONOMY_VERSION = "CONTENT_TAXONOMY_V1"
DEFAULT_CLASSIFIER_VERSION = "LOCAL_KEYWORD_V1"


DEFAULT_TOPICS: tuple[dict, ...] = (
    {"code": "FOOD_DRINK", "name": "Food & Drink", "keywords": ["food", "món ăn", "ẩm thực", "đồ uống", "restaurant", "美食", "餐厅"], "order": 10},
    {"code": "COOKING_RECIPES", "name": "Cooking & Recipes", "parent": "FOOD_DRINK", "keywords": ["công thức", "nấu ăn", "recipe", "cook", "nguyên liệu", "厨房", "食谱", "做法"], "order": 11},
    {"code": "BEAUTY_PERSONAL_CARE", "name": "Beauty & Personal Care", "keywords": ["làm đẹp", "beauty", "mỹ phẩm", "cosmetic", "护肤", "美容"], "order": 20},
    {"code": "SKINCARE", "name": "Skincare", "parent": "BEAUTY_PERSONAL_CARE", "keywords": ["dưỡng da", "skincare", "serum", "kem chống nắng", "mụn", "护肤", "防晒"], "order": 21},
    {"code": "MAKEUP", "name": "Makeup", "parent": "BEAUTY_PERSONAL_CARE", "keywords": ["trang điểm", "makeup", "son môi", "foundation", "化妆", "口红"], "order": 22},
    {"code": "FASHION", "name": "Fashion", "keywords": ["thời trang", "quần áo", "outfit", "fashion", "váy", "giày", "服装", "穿搭"], "order": 30},
    {"code": "HOME_LIVING", "name": "Home & Living", "keywords": ["gia dụng", "nhà cửa", "nội thất", "home", "kitchen", "家居", "家庭"], "order": 40},
    {"code": "HOME_APPLIANCES", "name": "Home Appliances", "parent": "HOME_LIVING", "keywords": ["máy hút bụi", "nồi chiên", "máy xay", "appliance", "đồ gia dụng", "家电"], "order": 41},
    {"code": "TECHNOLOGY", "name": "Technology", "keywords": ["công nghệ", "technology", "điện tử", "thiết bị", "科技", "电子"], "order": 50},
    {"code": "MOBILE_GADGETS", "name": "Mobile & Gadgets", "parent": "TECHNOLOGY", "keywords": ["điện thoại", "smartphone", "tai nghe", "sạc", "laptop", "手机", "耳机"], "order": 51},
    {"code": "HEALTH_FITNESS", "name": "Health & Fitness", "keywords": ["sức khỏe", "fitness", "tập luyện", "giảm cân", "workout", "健康", "健身"], "order": 60},
    {"code": "TRAVEL", "name": "Travel", "keywords": ["du lịch", "travel", "khách sạn", "địa điểm", "旅行", "景点"], "order": 70},
    {"code": "EDUCATION", "name": "Education", "keywords": ["học tập", "education", "hướng dẫn", "tutorial", "kiến thức", "学习", "教程"], "order": 80},
    {"code": "PETS", "name": "Pets", "keywords": ["thú cưng", "chó", "mèo", "pet", "dog", "cat", "宠物", "猫", "狗"], "order": 90},
    {"code": "ENTERTAINMENT", "name": "Entertainment", "keywords": ["giải trí", "hài", "âm nhạc", "entertainment", "music", "搞笑", "音乐"], "order": 100},
    {"code": "GENERAL_OTHER", "name": "General / Other", "keywords": [], "order": 999},
)


class ContentIntelligenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ClassificationResult:
    primary_topic: TopicCategory
    confidence: float
    secondary_topics: list[dict]
    evidence: list[dict]
    rationale: str
    metadata: dict


def normalize_for_matching(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^\w\s]", " ", without_marks).split())


def evidence_fingerprint(evidence: list[dict]) -> str:
    canonical = [
        {
            "source": item.get("source"),
            "source_id": item.get("source_id"),
            "text": item.get("text"),
            "language_code": item.get("language_code"),
        }
        for item in evidence
    ]
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LocalKeywordTopicClassifier:
    """Deterministic local baseline; provider boundary can later host an LLM safely."""

    SOURCE_WEIGHTS = {
        "PUBLICATION_TITLE": 1.4,
        "PUBLICATION_CAPTION": 1.3,
        "DRAFT_TITLE": 1.3,
        "DRAFT_CAPTION": 1.2,
        "SOURCE_CAPTION": 1.1,
        "TRANSCRIPT": 1.0,
        "OCR": 0.8,
    }

    def classify(self, *, evidence: list[dict], topics: list[TopicCategory]) -> ClassificationResult:
        if not evidence:
            raise ContentIntelligenceError("classification_no_evidence", "No caption, transcript, or OCR evidence is available")
        active_topics = [topic for topic in topics if topic.is_active]
        if not active_topics:
            raise ContentIntelligenceError("classification_taxonomy_empty", "The active taxonomy has no topics")

        scores: dict[UUID, float] = {topic.id: 0.0 for topic in active_topics}
        scored_evidence: list[dict] = []
        matched_sources: set[str] = set()
        matched_keyword_count = 0
        for item in evidence:
            normalized_text = normalize_for_matching(str(item.get("text") or ""))
            evidence_matches: list[str] = []
            source = str(item.get("source") or "")
            weight = self.SOURCE_WEIGHTS.get(source, 0.7)
            for topic in active_topics:
                for raw_keyword in topic.keywords_json or []:
                    keyword = normalize_for_matching(str(raw_keyword))
                    if not keyword or (keyword.isascii() and len(keyword) < 3) or keyword not in normalized_text:
                        continue
                    scores[topic.id] += weight * (1.0 + min(len(keyword), 24) / 48.0)
                    evidence_matches.append(f"{topic.code}:{raw_keyword}")
                    matched_keyword_count += 1
            scored_evidence.append({**item, "matched_keywords": evidence_matches[:20]})
            if evidence_matches:
                matched_sources.add(source)

        ranked = sorted(active_topics, key=lambda topic: (-scores[topic.id], topic.sort_order, topic.code))
        positive = [topic for topic in ranked if scores[topic.id] > 0]
        if not positive:
            fallback = next((topic for topic in active_topics if topic.code == "GENERAL_OTHER"), ranked[0])
            return ClassificationResult(
                primary_topic=fallback,
                confidence=0.2,
                secondary_topics=[],
                evidence=[{**item, "matched_keywords": []} for item in evidence],
                rationale="No taxonomy keyword matched; operator review is required.",
                metadata={"provider": "LOCAL_KEYWORD", "network_used": False},
            )

        primary = positive[0]
        primary_score = scores[primary.id]
        second_score = scores[positive[1].id] if len(positive) > 1 else 0.0
        margin = (primary_score - second_score) / primary_score if primary_score else 0.0
        confidence = min(
            0.97,
            0.42 + min(primary_score, 6.0) * 0.065 + min(len(matched_sources), 3) * 0.055 + margin * 0.12,
        )
        secondary = [
            {
                "topic_id": str(topic.id),
                "code": topic.code,
                "name": topic.name,
                "score": round(scores[topic.id], 4),
            }
            for topic in positive[1:4]
            if scores[topic.id] >= primary_score * 0.3
        ]
        return ClassificationResult(
            primary_topic=primary,
            confidence=round(confidence, 4),
            secondary_topics=secondary,
            evidence=scored_evidence,
            rationale=(
                f"Matched {matched_keyword_count} taxonomy keyword(s) across "
                f"{len(matched_sources)} evidence source type(s)."
            ),
            metadata={"provider": "LOCAL_KEYWORD", "network_used": False},
        )


class ContentClassificationService:
    def __init__(self, db: Session, *, classifier: LocalKeywordTopicClassifier | None = None):
        self.db = db
        self.classifier = classifier or LocalKeywordTopicClassifier()

    def ensure_default_taxonomy(
        self,
        workspace_id: UUID,
        taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
    ) -> list[TopicCategory]:
        existing = list(
            self.db.scalars(
                select(TopicCategory).where(
                    TopicCategory.workspace_id == workspace_id,
                    TopicCategory.taxonomy_version == taxonomy_version,
                )
            )
        )
        by_code = {topic.code: topic for topic in existing}
        for definition in DEFAULT_TOPICS:
            if definition["code"] in by_code:
                continue
            topic = TopicCategory(
                workspace_id=workspace_id,
                taxonomy_version=taxonomy_version,
                code=definition["code"],
                name=definition["name"],
                keywords_json=list(definition["keywords"]),
                sort_order=definition["order"],
                is_active=True,
                metadata_json={"seed_source": "CONTENT_TAXONOMY_V1"},
            )
            self.db.add(topic)
            by_code[topic.code] = topic
        self.db.flush()
        for definition in DEFAULT_TOPICS:
            parent_code = definition.get("parent")
            topic = by_code[definition["code"]]
            if parent_code and topic.parent_id is None:
                topic.parent_id = by_code[parent_code].id
        self.db.flush()
        return sorted(by_code.values(), key=lambda topic: (topic.sort_order, topic.code))

    def list_topics(
        self,
        workspace_id: UUID,
        *,
        taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
        include_inactive: bool = False,
    ) -> list[TopicCategory]:
        self.ensure_default_taxonomy(workspace_id, taxonomy_version)
        self.db.commit()
        filters = [
            TopicCategory.workspace_id == workspace_id,
            TopicCategory.taxonomy_version == taxonomy_version,
        ]
        if not include_inactive:
            filters.append(TopicCategory.is_active.is_(True))
        return list(
            self.db.scalars(
                select(TopicCategory)
                .where(*filters)
                .order_by(TopicCategory.sort_order.asc(), TopicCategory.name.asc())
            )
        )

    def create_topic(self, workspace_id: UUID, request: TopicCategoryCreateRequest) -> TopicCategory:
        self.ensure_default_taxonomy(workspace_id, request.taxonomy_version)
        self._validate_parent(workspace_id, request.taxonomy_version, request.parent_id)
        topic = TopicCategory(
            workspace_id=workspace_id,
            taxonomy_version=request.taxonomy_version,
            code=request.code,
            name=request.name.strip(),
            description=(request.description or "").strip() or None,
            parent_id=request.parent_id,
            keywords_json=request.keywords,
            sort_order=request.sort_order,
            is_active=request.is_active,
            metadata_json={"source": "OPERATOR_CREATED"},
        )
        self.db.add(topic)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ContentIntelligenceError("topic_code_exists", "A topic with this code already exists in the taxonomy version") from exc
        self.db.refresh(topic)
        logger.info("content_topic_created", extra={"workspace_id": str(workspace_id), "topic_id": str(topic.id), "topic_code": topic.code})
        return topic

    def update_topic(
        self,
        workspace_id: UUID,
        topic_id: UUID,
        request: TopicCategoryUpdateRequest,
    ) -> TopicCategory:
        topic = self.db.get(TopicCategory, topic_id)
        if topic is None or topic.workspace_id != workspace_id:
            raise ContentIntelligenceError("topic_not_found", "Topic was not found")
        if "parent_id" in request.model_fields_set:
            if request.parent_id == topic.id:
                raise ContentIntelligenceError("topic_parent_invalid", "A topic cannot be its own parent")
            self._validate_parent(workspace_id, topic.taxonomy_version, request.parent_id)
            topic.parent_id = request.parent_id
        for field_name in ("name", "description", "sort_order", "is_active"):
            if field_name in request.model_fields_set:
                value = getattr(request, field_name)
                if field_name == "name" and isinstance(value, str):
                    value = value.strip()
                setattr(topic, field_name, value)
        if request.keywords is not None:
            topic.keywords_json = request.keywords
        topic.metadata_json = {**(topic.metadata_json or {}), "last_operator_edit_at": datetime.now(UTC).isoformat()}
        self.db.commit()
        self.db.refresh(topic)
        logger.info("content_topic_updated", extra={"workspace_id": str(workspace_id), "topic_id": str(topic.id), "topic_code": topic.code})
        return topic

    def collect_evidence(self, publication: PlatformPublication) -> list[dict]:
        evidence: list[dict] = []
        metadata = publication.metadata_json or {}
        self._append_evidence(evidence, "PUBLICATION_TITLE", publication.id, metadata.get("external_title"))
        self._append_evidence(evidence, "PUBLICATION_CAPTION", publication.id, metadata.get("external_caption"))

        draft = self.db.get(PublishDraft, publication.publish_draft_id) if publication.publish_draft_id else None
        if draft is not None and draft.workspace_id == publication.workspace_id:
            self._append_evidence(evidence, "DRAFT_TITLE", draft.id, draft.title, getattr(draft, "language_code", None))
            self._append_evidence(evidence, "DRAFT_CAPTION", draft.id, draft.caption, getattr(draft, "language_code", None))

        source_video_id = publication.source_video_id or getattr(draft, "source_video_id", None)
        source = self.db.get(SourceVideo, source_video_id) if source_video_id else None
        if source is not None and source.workspace_id == publication.workspace_id:
            self._append_evidence(evidence, "SOURCE_CAPTION", source.id, source.caption, source.language_code)
            transcripts = list(
                self.db.scalars(
                    select(TranscriptSegment)
                    .where(
                        TranscriptSegment.source_video_id == source.id,
                        TranscriptSegment.is_current.is_(True),
                        TranscriptSegment.status != TranscriptSegmentStatus.REJECTED,
                    )
                    .order_by(TranscriptSegment.segment_index.asc())
                )
            )
            for segment in transcripts:
                self._append_evidence(
                    evidence,
                    "TRANSCRIPT",
                    segment.id,
                    segment.normalized_text or segment.text,
                    segment.language_code,
                    segment.confidence,
                )
            ocr_objects = list(
                self.db.scalars(
                    select(OcrTextObject)
                    .where(
                        OcrTextObject.source_video_id == source.id,
                        OcrTextObject.status != OcrObjectStatus.REJECTED,
                    )
                    .order_by(OcrTextObject.first_seen_ms.asc().nullslast(), OcrTextObject.created_at.asc())
                )
            )
            for ocr in ocr_objects:
                self._append_evidence(
                    evidence,
                    "OCR",
                    ocr.id,
                    ocr.normalized_text or ocr.text,
                    ocr.language_code,
                    ocr.confidence,
                )
        return evidence[:250]

    def enqueue(
        self,
        publication_id: UUID,
        workspace_id: UUID,
        request: ContentClassificationRunRequest,
    ) -> tuple[ContentClassification | None, Job | None, bool]:
        publication = self._publication(publication_id, workspace_id)
        self.ensure_default_taxonomy(workspace_id, request.taxonomy_version)
        ai_config, prompt = ContentAiSettingsService(self.db).get_runtime(workspace_id)
        if ai_config.enabled and ai_config.mode == "AI_ONLY" and not request.external_network_authorized:
            raise ContentIntelligenceError(
                "classification_ai_authorization_required",
                "AI-only mode requires explicit operator authorization before content can leave this workspace",
            )
        evidence = self.collect_evidence(publication)
        if not evidence:
            raise ContentIntelligenceError(
                "classification_no_evidence",
                "Add a publication caption or link the Reel to a source with transcript/OCR before classifying",
            )
        effective_classifier_version = request.classifier_version
        if request.external_network_authorized and ai_config.enabled and ai_config.mode != "LOCAL_ONLY":
            effective_classifier_version = f"{request.classifier_version}:{prompt['version']}"[:80]
        fingerprint = evidence_fingerprint(evidence)
        existing = self.db.scalar(
            select(ContentClassification).where(
                ContentClassification.platform_publication_id == publication.id,
                ContentClassification.taxonomy_version == request.taxonomy_version,
                ContentClassification.classifier_version == effective_classifier_version,
                ContentClassification.input_fingerprint_sha256 == fingerprint,
            )
        )
        if existing is not None:
            self.db.execute(
                update(ContentClassification)
                .where(
                    ContentClassification.platform_publication_id == publication.id,
                    ContentClassification.id != existing.id,
                    ContentClassification.is_current.is_(True),
                )
                .values(is_current=False)
            )
            existing.is_current = True
            self.db.commit()
            return existing, None, True

        idempotency_key = (
            f"content-classification:{publication.id}:{request.taxonomy_version}:"
            f"{effective_classifier_version}:{fingerprint[:20]}"
        )
        existing_job = self.db.scalar(
            select(Job).where(
                Job.workspace_id == workspace_id,
                Job.idempotency_key == idempotency_key,
            )
        )
        if existing_job is not None:
            self.db.commit()
            return None, JobService(self.db).get_job(existing_job.id), True

        job = JobService(self.db).create_job(
            workspace_id=workspace_id,
            job_type=JobType.CLASSIFY_CONTENT,
            source_video_id=publication.source_video_id,
            reference_type="platform_publication_content_classification",
            reference_id=publication.id,
            idempotency_key=idempotency_key,
            max_attempts=2,
            payload_json={
                "platform_publication_id": str(publication.id),
                "taxonomy_version": request.taxonomy_version,
                "classifier_version": effective_classifier_version,
                "input_fingerprint_sha256": fingerprint,
                "evidence_source_count": len(evidence),
                "external_network_authorized": request.external_network_authorized,
            },
        )
        logger.info(
            "content_classification_job_created",
            extra={"workspace_id": str(workspace_id), "publication_id": str(publication.id), "job_id": str(job.id)},
        )
        return None, job, False

    def execute_job(self, job_id: UUID) -> ContentClassification:
        job = JobService(self.db).get_job(job_id)
        if job.job_type != JobType.CLASSIFY_CONTENT:
            raise ContentIntelligenceError("classification_job_type_invalid", "Job is not a content classification job")
        payload = job.payload_json or {}
        try:
            publication_id = UUID(str(payload["platform_publication_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise ContentIntelligenceError("classification_publication_missing", "Classification job is missing its publication id") from exc
        publication = self._publication(publication_id, job.workspace_id)
        taxonomy_version = str(payload.get("taxonomy_version") or DEFAULT_TAXONOMY_VERSION)
        classifier_version = str(payload.get("classifier_version") or DEFAULT_CLASSIFIER_VERSION)
        topics = self.ensure_default_taxonomy(job.workspace_id, taxonomy_version)
        evidence = self.collect_evidence(publication)
        if not evidence:
            raise ContentIntelligenceError("classification_no_evidence", "No persisted evidence is available for classification")
        fingerprint = evidence_fingerprint(evidence)
        existing = self.db.scalar(
            select(ContentClassification).where(
                ContentClassification.platform_publication_id == publication.id,
                ContentClassification.taxonomy_version == taxonomy_version,
                ContentClassification.classifier_version == classifier_version,
                ContentClassification.input_fingerprint_sha256 == fingerprint,
            )
        )
        if existing is not None:
            self.db.execute(
                update(ContentClassification)
                .where(
                    ContentClassification.platform_publication_id == publication.id,
                    ContentClassification.id != existing.id,
                    ContentClassification.is_current.is_(True),
                )
                .values(is_current=False)
            )
            existing.is_current = True
            job.result_json = {
                "content_classification_id": str(existing.id),
                "resumed_from_existing_classification": True,
            }
            self.db.commit()
            return existing

        from src.content_intelligence.services.content_ai_classifier import ContentAiClassifierError, LocalOrAiTopicClassifier
        ai_config, prompt = ContentAiSettingsService(self.db).get_runtime(job.workspace_id)
        local_result = self.classifier.classify(evidence=evidence, topics=topics)
        use_ai_authorized = bool(payload.get("external_network_authorized"))
        use_ai = (
            use_ai_authorized
            and ai_config.enabled
            and ai_config.mode != "LOCAL_ONLY"
        )
        result = local_result
        if ai_config.mode == "AI_ONLY" and use_ai:
            use_ai = True
        if use_ai and (ai_config.mode == "AI_ONLY" or local_result.confidence < ai_config.local_confidence_threshold):
            try:
                result = LocalOrAiTopicClassifier().classify_with_ai(
                    evidence=evidence,
                    topics=topics,
                    config=ai_config,
                    prompt=prompt,
                )
            except ContentAiClassifierError as exc:
                if ai_config.fallback_mode != "local_keyword":
                    raise ContentIntelligenceError(exc.code, str(exc)) from exc
                result = ClassificationResult(
                    primary_topic=local_result.primary_topic,
                    confidence=local_result.confidence,
                    secondary_topics=local_result.secondary_topics,
                    evidence=local_result.evidence,
                    rationale=f"AI classification failed; local keyword fallback used. {local_result.rationale}",
                    metadata={
                        "provider": "LOCAL_KEYWORD",
                        "network_used": False,
                        "fallback_from": "AI",
                        "prompt_version": str(prompt.get("version") or "unknown"),
                    },
                )
        self.db.execute(
            update(ContentClassification)
            .where(
                ContentClassification.platform_publication_id == publication.id,
                ContentClassification.is_current.is_(True),
            )
            .values(is_current=False)
        )
        classification = ContentClassification(
            workspace_id=job.workspace_id,
            platform_publication_id=publication.id,
            source_video_id=publication.source_video_id,
            taxonomy_version=taxonomy_version,
            classifier_version=classifier_version,
            input_fingerprint_sha256=fingerprint,
            decision_status="NEEDS_REVIEW",
            primary_topic_id=result.primary_topic.id,
            primary_topic_code=result.primary_topic.code,
            confidence=result.confidence,
            secondary_topics_json=result.secondary_topics,
            evidence_json=result.evidence,
            rationale=result.rationale,
            created_by_job_id=job.id,
            is_current=True,
            metadata_json={
                **(result.metadata or {}),
                "evidence_source_count": len(evidence),
            },
        )
        self.db.add(classification)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            recovered = self.db.scalar(
                select(ContentClassification).where(
                    ContentClassification.platform_publication_id == publication.id,
                    ContentClassification.taxonomy_version == taxonomy_version,
                    ContentClassification.classifier_version == classifier_version,
                    ContentClassification.input_fingerprint_sha256 == fingerprint,
                )
            )
            if recovered is None:
                raise
            return recovered
        job.result_json = {
            "content_classification_id": str(classification.id),
            "primary_topic_code": classification.primary_topic_code,
            "confidence": classification.confidence,
            "network_used": bool((result.metadata or {}).get("network_used")),
            "provider": str((result.metadata or {}).get("provider") or "LOCAL_KEYWORD"),
            "prompt_version": (result.metadata or {}).get("prompt_version"),
        }
        self.db.commit()
        self.db.refresh(classification)
        logger.info(
            "content_classification_completed",
            extra={
                "workspace_id": str(job.workspace_id),
                "publication_id": str(publication.id),
                "classification_id": str(classification.id),
                "topic_code": classification.primary_topic_code,
                "confidence": classification.confidence,
            },
        )
        return classification

    def get_current(self, publication_id: UUID, workspace_id: UUID) -> ContentClassification | None:
        self._publication(publication_id, workspace_id)
        return self.db.scalar(
            select(ContentClassification).where(
                ContentClassification.workspace_id == workspace_id,
                ContentClassification.platform_publication_id == publication_id,
                ContentClassification.is_current.is_(True),
            )
        )

    def review_queue(
        self,
        workspace_id: UUID,
        *,
        platform_account_id: UUID | None = None,
        decision_status: str | None = None,
        low_confidence_only: bool = False,
        confidence_threshold: float = 0.6,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[tuple[PlatformPublication, PlatformAccount, ContentClassification | None]], int, dict, dict[UUID, Job]]:
        join_condition = and_(
            ContentClassification.platform_publication_id == PlatformPublication.id,
            ContentClassification.is_current.is_(True),
        )
        filters = [PlatformPublication.workspace_id == workspace_id]
        if platform_account_id is not None:
            filters.append(PlatformPublication.platform_account_id == platform_account_id)
        if decision_status == "UNCLASSIFIED":
            filters.append(ContentClassification.id.is_(None))
        elif decision_status:
            filters.append(ContentClassification.decision_status == decision_status)
        if low_confidence_only:
            filters.append(ContentClassification.confidence < confidence_threshold)
        cleaned_query = (query or "").strip()
        if cleaned_query:
            pattern = f"%{cleaned_query}%"
            filters.append(
                or_(
                    PlatformPublication.external_publish_id.ilike(pattern),
                    PlatformPublication.external_reel_id.ilike(pattern),
                    PlatformAccount.display_name.ilike(pattern),
                    cast(PlatformPublication.metadata_json["external_caption"], String).ilike(pattern),
                )
            )
        base = (
            select(PlatformPublication, PlatformAccount, ContentClassification)
            .join(PlatformAccount, PlatformAccount.id == PlatformPublication.platform_account_id)
            .outerjoin(ContentClassification, join_condition)
            .where(*filters)
        )
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = list(
            self.db.execute(
                base.order_by(
                    ContentClassification.decision_status.asc().nullsfirst(),
                    ContentClassification.confidence.asc().nullsfirst(),
                    PlatformPublication.published_at.desc().nullslast(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
        )
        publication_ids = [publication.id for publication, _account, _classification in rows]
        latest_jobs: dict[UUID, Job] = {}
        if publication_ids:
            for job in self.db.scalars(
                select(Job)
                .where(
                    Job.workspace_id == workspace_id,
                    Job.reference_type == "platform_publication_content_classification",
                    Job.reference_id.in_(publication_ids),
                )
                .order_by(Job.created_at.desc())
            ):
                if job.reference_id is not None and job.reference_id not in latest_jobs:
                    latest_jobs[job.reference_id] = job

        total_publications = int(
            self.db.scalar(
                select(func.count()).select_from(PlatformPublication).where(PlatformPublication.workspace_id == workspace_id)
            )
            or 0
        )
        status_counts = {
            str(status): int(count)
            for status, count in self.db.execute(
                select(ContentClassification.decision_status, func.count(distinct(ContentClassification.platform_publication_id)))
                .where(
                    ContentClassification.workspace_id == workspace_id,
                    ContentClassification.is_current.is_(True),
                )
                .group_by(ContentClassification.decision_status)
            ).all()
        }
        classified_count = sum(status_counts.values())
        low_confidence_count = int(
            self.db.scalar(
                select(func.count(distinct(ContentClassification.platform_publication_id))).where(
                    ContentClassification.workspace_id == workspace_id,
                    ContentClassification.is_current.is_(True),
                    ContentClassification.confidence < confidence_threshold,
                )
            )
            or 0
        )
        kpis = {
            "total_publications": total_publications,
            "unclassified_count": max(0, total_publications - classified_count),
            "needs_review_count": status_counts.get("NEEDS_REVIEW", 0),
            "approved_count": status_counts.get("APPROVED", 0),
            "overridden_count": status_counts.get("OVERRIDDEN", 0),
            "low_confidence_count": low_confidence_count,
        }
        return rows, total, kpis, latest_jobs

    def decide(
        self,
        classification_id: UUID,
        workspace_id: UUID,
        operator_subject: str,
        request: ContentClassificationDecisionRequest,
    ) -> ContentClassification:
        classification = self.db.get(ContentClassification, classification_id)
        if classification is None or classification.workspace_id != workspace_id or not classification.is_current:
            raise ContentIntelligenceError("classification_not_found", "Current classification was not found")
        if request.decision == "OVERRIDDEN":
            primary = self._topic(
                workspace_id,
                classification.taxonomy_version,
                request.primary_topic_id,
                require_active=True,
            )
            classification.primary_topic_id = primary.id
            classification.primary_topic_code = primary.code
            secondary: list[dict] = []
            for topic_id in dict.fromkeys(request.secondary_topic_ids):
                if topic_id == primary.id:
                    continue
                topic = self._topic(workspace_id, classification.taxonomy_version, topic_id, require_active=True)
                secondary.append({"topic_id": str(topic.id), "code": topic.code, "name": topic.name, "source": "OPERATOR"})
            classification.secondary_topics_json = secondary
            classification.override_reason = (request.reason or "").strip()
        else:
            classification.override_reason = None
        classification.decision_status = request.decision
        classification.reviewed_by = operator_subject[:180]
        classification.reviewed_at = datetime.now(UTC)
        classification.metadata_json = {
            **(classification.metadata_json or {}),
            "operator_reviewed": True,
        }
        self.db.commit()
        self.db.refresh(classification)
        logger.info(
            "content_classification_decided",
            extra={
                "workspace_id": str(workspace_id),
                "classification_id": str(classification.id),
                "decision": classification.decision_status,
                "topic_code": classification.primary_topic_code,
            },
        )
        return classification

    def topic_name(self, topic_id: UUID | None) -> str | None:
        if topic_id is None:
            return None
        topic = self.db.get(TopicCategory, topic_id)
        return topic.name if topic is not None else None

    def _publication(self, publication_id: UUID, workspace_id: UUID) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, publication_id)
        if publication is None or publication.workspace_id != workspace_id:
            raise ContentIntelligenceError("classification_publication_not_found", "Platform publication was not found")
        return publication

    def _validate_parent(self, workspace_id: UUID, taxonomy_version: str, parent_id: UUID | None) -> None:
        if parent_id is not None:
            self._topic(workspace_id, taxonomy_version, parent_id, require_active=False)

    def _topic(
        self,
        workspace_id: UUID,
        taxonomy_version: str,
        topic_id: UUID | None,
        *,
        require_active: bool,
    ) -> TopicCategory:
        topic = self.db.get(TopicCategory, topic_id) if topic_id else None
        if (
            topic is None
            or topic.workspace_id != workspace_id
            or topic.taxonomy_version != taxonomy_version
            or (require_active and not topic.is_active)
        ):
            raise ContentIntelligenceError("topic_not_found", "Topic was not found in the active taxonomy")
        return topic

    @staticmethod
    def _append_evidence(
        target: list[dict],
        source: str,
        source_id: UUID | None,
        raw_text: object,
        language_code: str | None = None,
        confidence: float | None = None,
    ) -> None:
        text = " ".join(str(raw_text or "").split())[:1200]
        if not text:
            return
        normalized = normalize_for_matching(text)
        if any(item.get("source") == source and normalize_for_matching(str(item.get("text") or "")) == normalized for item in target):
            return
        target.append(
            {
                "source": source,
                "source_id": str(source_id) if source_id else None,
                "text": text,
                "language_code": language_code,
                "confidence": confidence,
                "matched_keywords": [],
            }
        )
