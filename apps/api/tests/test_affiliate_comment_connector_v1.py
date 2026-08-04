from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from types import SimpleNamespace
import unittest
from urllib import parse
from uuid import uuid4


from src.affiliate_intelligence.services.affiliate_comment_service import AffiliateCommentError, AffiliateCommentService
from src.enums import JobStatus, JobType, PlatformAccountStatus, PublishTargetPlatform
from src.growth_intelligence.services.growth_score_service import GrowthScoreService
from src.publish.connectors.base import PublishConnectorError
from src.publish.connectors.facebook_reels import FacebookReelsConnector
from src.publish.types import PlatformAccountConfig
from src.schemas.affiliate_comment import AffiliateCommentPreviewRequest
from src.services.job_templates import get_step_templates


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return b'{"id":"comment-123"}'


class _SnapshotSession:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    def scalars(self, _statement):
        return self.snapshots


class _ApprovalSession:
    def __init__(self, placement, existing_job, scalar_job=None, previous_placement=None):
        self.placement = placement
        self.previous_placement = previous_placement
        self.existing_job = existing_job
        self.scalar_job = existing_job if scalar_job is None else scalar_job
        self.commits = 0

    def get(self, _model, object_id):
        if object_id == self.placement.id:
            return self.placement
        if self.previous_placement is not None and object_id == self.previous_placement.id:
            return self.previous_placement
        if self.existing_job is not None and object_id == self.existing_job.id:
            return self.existing_job
        return None

    def scalar(self, _statement):
        return self.scalar_job

    def scalars(self, _statement):
        return [self.previous_placement] if self.previous_placement is not None else []

    def commit(self):
        self.commits += 1


class _PreviewSession:
    def __init__(self, current, posted_history=None):
        self.current = current
        self.posted_history = list(posted_history or [])
        # Active-template lookup, idempotent-preview lookup, current placement.
        self.scalar_results = [None, None, current]
        self.added = None
        self.commits = 0

    def scalar(self, _statement):
        return self.scalar_results.pop(0)

    def scalars(self, _statement):
        return list(self.posted_history)

    def execute(self, _statement):
        if self.current is not None:
            self.current.is_current = False

    def add(self, value):
        self.added = value

    def flush(self):
        if self.added is not None and self.added.id is None:
            self.added.id = uuid4()

    def commit(self):
        self.commits += 1

    def refresh(self, _value):
        pass


class AffiliateCommentConnectorV1Tests(unittest.TestCase):
    def test_connector_posts_message_with_bearer_header_and_no_query_token(self) -> None:
        connector = FacebookReelsConnector()
        calls = []

        def fake_urlopen(req, timeout=120):
            calls.append(req)
            self.assertTrue(req.full_url.endswith("/v20.0/reel-123/comments"))
            self.assertNotIn("access_token", req.full_url)
            self.assertEqual(req.headers["Authorization"], "Bearer page-token")
            form = parse.parse_qs(req.data.decode("utf-8"))
            self.assertEqual(form["message"], ["CTA\nhttps://example.com/a\nAffiliate disclosure"])
            self.assertEqual(form["attachment_url"], ["https://cdn.example.com/product.jpg"])
            return _FakeResponse()

        module = __import__("src.publish.connectors.facebook_reels", fromlist=["request"])
        original = module.request.urlopen
        module.request.urlopen = fake_urlopen
        try:
            result = connector.post_affiliate_comment(
                account=PlatformAccountConfig(
                    platform_account_id=uuid4(),
                    platform=PublishTargetPlatform.FACEBOOK_REELS,
                    page_id="page-123",
                    display_name="Page",
                    access_token="page-token",
                ),
                external_reel_id="reel-123",
                message="CTA\nhttps://example.com/a\nAffiliate disclosure",
                attachment_image_url="https://cdn.example.com/product.jpg",
            )
        finally:
            module.request.urlopen = original

        self.assertEqual(result["external_comment_id"], "comment-123")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("page-token", repr(result))

    def test_connector_fails_closed_without_reel_or_message(self) -> None:
        account = PlatformAccountConfig(
            platform_account_id=uuid4(),
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            page_id="page-123",
            display_name="Page",
            access_token="token",
        )
        with self.assertRaises(PublishConnectorError):
            FacebookReelsConnector().post_affiliate_comment(account=account, external_reel_id="", message="test")
        with self.assertRaises(PublishConnectorError):
            FacebookReelsConnector().post_affiliate_comment(account=account, external_reel_id="reel", message="")
        with self.assertRaises(PublishConnectorError) as raised:
            FacebookReelsConnector().post_affiliate_comment(
                account=account,
                external_reel_id="reel",
                message="message",
                attachment_image_url="http://localhost/product.jpg",
            )
        self.assertEqual(raised.exception.code, "invalid_comment_attachment")

    def test_preview_schema_allows_optional_disclosure(self) -> None:
        request = AffiliateCommentPreviewRequest(
            cta_text="CTA",
            disclosure_text="",
            comment_source="ITEM_CUSTOM",
            comment_message_template_override="{{cta}}\n{{affiliate_url}}",
        )
        self.assertEqual(request.disclosure_text, "")
        self.assertEqual(request.comment_message_template_override, "{{cta}}\n{{affiliate_url}}")

    def test_comment_gate_requires_priority_and_verified_page_capability(self) -> None:
        now = datetime.now(UTC)
        snapshot = SimpleNamespace(
            id=uuid4(),
            observed_at=now,
            payload_hash_sha256="a" * 64,
            derivation_version="PUBLICATION_METRICS_V2",
            views_per_hour=100,
            engagement_delta_rate_percent=5,
            data_quality="COMPLETE",
            is_estimated=False,
        )
        assessment = SimpleNamespace(
            id=uuid4(),
            status="READY",
            confidence="HIGH",
            growth_score=80,
            input_fingerprint_sha256=GrowthScoreService.input_fingerprint([snapshot]),
        )
        context = {
            "publication": SimpleNamespace(
                platform=PublishTargetPlatform.FACEBOOK_REELS,
                external_reel_id="reel-1",
                external_publish_id="reel-1",
                external_media_id=None,
                id=uuid4(),
            ),
            "account": SimpleNamespace(
                status=PlatformAccountStatus.ACTIVE,
                is_on_hold=False,
                cooldown_until=None,
                metadata_json={
                    "facebook_publish_capability_verified": True,
                    "facebook_verified_publish_scopes": ["pages_manage_posts"],
                    "facebook_page_tasks": ["CREATE_CONTENT"],
                },
            ),
            "product_match": SimpleNamespace(selected_fit_score=80),
            "product": SimpleNamespace(
                is_active=True,
                availability_status="IN_STOCK",
                affiliate_url="https://example.com/affiliate-product",
            ),
            "assessment": assessment,
        }
        service = AffiliateCommentService(_SnapshotSession([snapshot]))  # type: ignore[arg-type]
        service._validate_gates(context)
        context["product_match"].selected_fit_score = 50
        with self.assertRaises(AffiliateCommentError) as raised:
            service._validate_gates(context)
        self.assertEqual(raised.exception.code, "affiliate_comment_not_priority")
        context["product_match"].selected_fit_score = 80
        context["product"].affiliate_url = "http://localhost:3000/publishing/settings/affiliate-catalog"
        with self.assertRaises(AffiliateCommentError) as invalid_url:
            service._validate_gates(context)
        self.assertEqual(invalid_url.exception.code, "affiliate_comment_url_invalid")

    def test_comment_job_has_one_network_boundary(self) -> None:
        self.assertEqual(
            [step.key for step in get_step_templates(JobType.POST_AFFILIATE_COMMENT)],
            ["validate_approval", "resolve_page_credential", "post_comment", "persist_result", "finalize"],
        )

    def test_draft_preview_edit_creates_a_new_audited_revision(self) -> None:
        workspace_id = uuid4()
        publication_id = uuid4()
        current = SimpleNamespace(
            id=uuid4(),
            status="DRAFT",
            is_current=True,
            metadata_json={"revision_number": 1},
        )
        session = _PreviewSession(current)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]
        publication = SimpleNamespace(
            id=publication_id,
            affiliate_comment_status=None,
            external_reel_id="reel-123",
            external_publish_id="reel-123",
            external_media_id=None,
        )
        context = {
            "publication": publication,
            "account": SimpleNamespace(id=uuid4()),
            "product_match": SimpleNamespace(id=uuid4(), selected_fit_score=82),
            "product": SimpleNamespace(id=uuid4(), name="Product", affiliate_url="https://example.com/product", image_url="https://cdn.example.com/product.jpg"),
            "assessment": SimpleNamespace(id=uuid4(), growth_score=84, confidence="HIGH"),
        }
        service._load_context = lambda *_args: context  # type: ignore[method-assign]
        service._validate_gates = lambda _context: None  # type: ignore[method-assign]

        replacement, reused = service.preview(
            publication_id,
            workspace_id,
            "operator@example.com",
            AffiliateCommentPreviewRequest(
                cta_text="CTA đã sửa",
                disclosure_text="Disclosure affiliate đã sửa",
                comment_source="ITEM_CUSTOM",
                comment_message_template_override="{{cta}}\n{{product_name}}\n{{affiliate_url}}\n{{product_image}}",
                replaces_placement_id=current.id,
            ),
        )

        self.assertFalse(reused)
        self.assertFalse(current.is_current)
        self.assertEqual(current.metadata_json["superseded_by_placement_id"], str(replacement.id))
        self.assertEqual(replacement.metadata_json["revision_number"], 2)
        self.assertEqual(replacement.metadata_json["replaces_placement_id"], str(current.id))
        self.assertEqual(replacement.attachment_image_url, "https://cdn.example.com/product.jpg")
        self.assertEqual(replacement.comment_message, "CTA đã sửa\nProduct\nhttps://example.com/product")
        self.assertEqual(replacement.metadata_json["comment_source"], "ITEM_CUSTOM")
        self.assertEqual(
            replacement.metadata_json["comment_message_template_override"],
            "{{cta}}\n{{product_name}}\n{{affiliate_url}}\n{{product_image}}",
        )
        self.assertTrue(replacement.metadata_json["comment_message_overridden"])
        self.assertIn(f":replace:{current.id}", replacement.idempotency_key)
        self.assertEqual(publication.affiliate_comment_status, "DRAFT")
        self.assertEqual(session.commits, 1)

    def test_custom_item_comment_can_create_the_first_preview_with_variables(self) -> None:
        workspace_id = uuid4()
        publication_id = uuid4()
        session = _PreviewSession(None)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]
        publication = SimpleNamespace(
            id=publication_id,
            caption="Reel title",
            affiliate_comment_status=None,
            external_reel_id="reel-custom",
            external_publish_id="reel-custom",
            external_media_id=None,
        )
        context = {
            "publication": publication,
            "account": SimpleNamespace(id=uuid4(), display_name="Page name"),
            "product_match": SimpleNamespace(id=uuid4(), selected_fit_score=82),
            "product": SimpleNamespace(
                id=uuid4(),
                name="Product",
                description="Description",
                affiliate_url="https://example.com/custom-product",
                image_url=None,
            ),
            "assessment": SimpleNamespace(id=uuid4(), growth_score=84, confidence="HIGH"),
        }
        service._load_context = lambda *_args: context  # type: ignore[method-assign]
        service._validate_gates = lambda _context: None  # type: ignore[method-assign]

        placement, reused = service.preview(
            publication_id,
            workspace_id,
            "operator@example.com",
            AffiliateCommentPreviewRequest(
                cta_text="CTA",
                disclosure_text="Disclosure",
                comment_source="ITEM_CUSTOM",
                comment_message_template_override="{{page_name}}\n{{reel_title}}\n{{product_name}}\n{{description}}\n{{affiliate_url}}",
                attach_product_image=False,
            ),
        )

        self.assertFalse(reused)
        self.assertEqual(
            placement.comment_message,
            "Page name\nReel title\nProduct\nDescription\nhttps://example.com/custom-product",
        )
        self.assertEqual(placement.metadata_json["comment_source"], "ITEM_CUSTOM")
        self.assertIsNone(placement.template_id)

    def test_custom_item_comment_auto_appends_affiliate_url_when_omitted(self) -> None:
        workspace_id = uuid4()
        publication_id = uuid4()
        session = _PreviewSession(None)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]
        publication = SimpleNamespace(
            id=publication_id,
            caption="Reel title",
            affiliate_comment_status=None,
            external_reel_id="reel-custom-auto-url",
            external_publish_id="reel-custom-auto-url",
            external_media_id=None,
        )
        context = {
            "publication": publication,
            "account": SimpleNamespace(id=uuid4(), display_name="Page name"),
            "product_match": SimpleNamespace(id=uuid4(), selected_fit_score=82),
            "product": SimpleNamespace(
                id=uuid4(),
                name="Product",
                description="Description",
                affiliate_url="https://s.shopee.vn/9zwaq5XFGX",
                image_url="https://cdn.example.com/product.jpg",
            ),
            "assessment": SimpleNamespace(id=uuid4(), growth_score=84, confidence="HIGH"),
        }
        service._load_context = lambda *_args: context  # type: ignore[method-assign]
        service._validate_gates = lambda _context: None  # type: ignore[method-assign]

        placement, reused = service.preview(
            publication_id,
            workspace_id,
            "operator@example.com",
            AffiliateCommentPreviewRequest(
                cta_text="CTA",
                disclosure_text="Disclosure",
                comment_source="ITEM_CUSTOM",
                comment_message_template_override="Mua sản phẩm: {{product_name}}",
                attach_product_image=True,
            ),
        )

        self.assertFalse(reused)
        self.assertEqual(
            placement.comment_message,
            "Mua sản phẩm: Product\n\nhttps://s.shopee.vn/9zwaq5XFGX",
        )
        self.assertTrue(placement.metadata_json["affiliate_url_auto_appended"])

    def test_posted_comment_can_start_a_distinct_second_draft(self) -> None:
        workspace_id = uuid4()
        publication_id = uuid4()
        previous_message = "Comment trước\n\nhttps://s.shopee.vn/old"
        previous = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            platform_publication_id=publication_id,
            status="POSTED",
            is_current=True,
            message_sha256=hashlib.sha256(previous_message.encode("utf-8")).hexdigest(),
            posted_at=datetime.now(UTC) - timedelta(hours=7),
            created_at=datetime.now(UTC) - timedelta(hours=7),
            metadata_json={"placement_sequence": 1, "revision_number": 1},
        )
        session = _PreviewSession(previous, [previous])
        service = AffiliateCommentService(session)  # type: ignore[arg-type]
        publication = SimpleNamespace(
            id=publication_id,
            caption="Reel title",
            affiliate_comment_status="POSTED",
            external_reel_id="reel-another",
            external_publish_id="reel-another",
            external_media_id=None,
        )
        context = {
            "publication": publication,
            "account": SimpleNamespace(id=uuid4(), display_name="Page name"),
            "product_match": SimpleNamespace(id=uuid4(), selected_fit_score=82),
            "product": SimpleNamespace(
                id=uuid4(),
                name="Product",
                description="Description",
                affiliate_url="https://s.shopee.vn/new-link",
                image_url=None,
            ),
            "assessment": SimpleNamespace(id=uuid4(), growth_score=84, confidence="HIGH"),
        }
        service._load_context = lambda *_args: context  # type: ignore[method-assign]
        service._validate_gates = lambda _context: None  # type: ignore[method-assign]

        placement, reused = service.preview(
            publication_id,
            workspace_id,
            "operator@example.com",
            AffiliateCommentPreviewRequest(
                cta_text="CTA",
                disclosure_text="",
                comment_source="ITEM_CUSTOM",
                comment_message_template_override="Nội dung mới {{product_name}}",
                attach_product_image=False,
                create_another_comment=True,
                previous_posted_placement_id=previous.id,
            ),
        )

        self.assertFalse(reused)
        self.assertFalse(previous.is_current)
        self.assertEqual(placement.status, "DRAFT")
        self.assertEqual(placement.metadata_json["placement_sequence"], 2)
        self.assertEqual(placement.metadata_json["previous_posted_placement_id"], str(previous.id))
        self.assertIsNone(placement.metadata_json["replaces_placement_id"])
        self.assertEqual(previous.metadata_json["next_comment_placement_id"], str(placement.id))
        self.assertNotIn("superseded_by_placement_id", previous.metadata_json)

    def test_second_comment_approval_respects_cooldown(self) -> None:
        workspace_id = uuid4()
        publication_id = uuid4()
        previous = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            platform_publication_id=publication_id,
            status="POSTED",
            message_sha256="a" * 64,
            posted_at=datetime.now(UTC) - timedelta(hours=1),
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        placement = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            platform_publication_id=publication_id,
            status="DRAFT",
            is_current=True,
            message_sha256="b" * 64,
            metadata_json={"previous_posted_placement_id": str(previous.id)},
        )
        service = AffiliateCommentService(
            _ApprovalSession(placement, None, previous_placement=previous)  # type: ignore[arg-type]
        )

        with self.assertRaises(AffiliateCommentError) as raised:
            service.approve_and_enqueue(placement.id, workspace_id, "operator@example.com")
        self.assertEqual(raised.exception.code, "affiliate_comment_cooldown")

    def test_second_comment_policy_limits_two_posts_per_24_hours(self) -> None:
        workspace_id = uuid4()
        publication_id = uuid4()
        posted = [
            SimpleNamespace(
                id=uuid4(),
                status="POSTED",
                message_sha256=str(index) * 64,
                posted_at=datetime.now(UTC) - timedelta(hours=index + 1),
                created_at=datetime.now(UTC) - timedelta(hours=index + 1),
            )
            for index in range(2)
        ]
        service = AffiliateCommentService(_PreviewSession(posted[0], posted))  # type: ignore[arg-type]
        _, policy = service._another_comment_policy(
            publication_id,
            workspace_id,
            current=posted[0],
            posted_history=posted,
        )
        self.assertFalse(policy["can_create_another"])
        self.assertFalse(policy["can_post_now"])
        self.assertEqual(policy["blocked_reason"], "DAILY_LIMIT")
        self.assertEqual(policy["posted_count_24h"], 2)

    def test_preview_edit_is_locked_after_the_job_is_queued(self) -> None:
        current = SimpleNamespace(id=uuid4(), status="QUEUED", is_current=True, metadata_json={})
        session = _PreviewSession(current)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]
        service._load_context = lambda *_args: {  # type: ignore[method-assign]
            "product": SimpleNamespace(name="Product", affiliate_url="https://example.com/product", image_url=None),
            "product_match": SimpleNamespace(id=uuid4()),
        }
        service._validate_gates = lambda _context: None  # type: ignore[method-assign]

        with self.assertRaises(AffiliateCommentError) as raised:
            service.preview(
                uuid4(),
                uuid4(),
                "operator@example.com",
                AffiliateCommentPreviewRequest(
                    cta_text="CTA đã sửa",
                    disclosure_text="Disclosure affiliate đã sửa",
                    replaces_placement_id=current.id,
                ),
            )

        self.assertEqual(raised.exception.code, "affiliate_comment_preview_locked")
        self.assertIsNone(session.added)

    def test_approval_reuses_an_existing_active_post_job(self) -> None:
        workspace_id = uuid4()
        publication_id = uuid4()
        placement = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            platform_publication_id=publication_id,
            affiliate_product_match_id=uuid4(),
            growth_assessment_id=uuid4(),
            message_sha256="a" * 64,
            comment_message="CTA\nhttps://example.com/affiliate-product",
            affiliate_url="https://example.com/affiliate-product",
            attach_product_image=False,
            attachment_image_url=None,
            is_current=True,
            status="DRAFT",
            post_job_id=None,
            approved_at=None,
            metadata_json={},
        )
        existing_job = SimpleNamespace(id=uuid4(), workspace_id=workspace_id, status=JobStatus.QUEUED)
        placement.post_job_id = existing_job.id
        terminal_base_job = SimpleNamespace(id=uuid4(), workspace_id=workspace_id, status=JobStatus.FAILED)
        session = _ApprovalSession(placement, existing_job, scalar_job=terminal_base_job)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]
        publication = SimpleNamespace(id=publication_id, source_video_id=uuid4(), affiliate_comment_status=None)
        service._load_context = lambda *_args: {  # type: ignore[method-assign]
            "publication": publication,
            "account": SimpleNamespace(id=uuid4()),
            "product_match": SimpleNamespace(id=placement.affiliate_product_match_id),
            "assessment": SimpleNamespace(id=placement.growth_assessment_id),
        }
        service._validate_gates = lambda _context: None  # type: ignore[method-assign]
        service.accounts.resolve_config = lambda _account_id: SimpleNamespace()  # type: ignore[method-assign]

        updated, job, reused = service.approve_and_enqueue(placement.id, workspace_id, "operator@example.com")

        self.assertTrue(reused)
        self.assertIs(job, existing_job)
        self.assertEqual(updated.post_job_id, existing_job.id)
        self.assertEqual(updated.status, "QUEUED")
        self.assertEqual(session.commits, 1)

    def test_approval_blocks_a_test_only_template_preview(self) -> None:
        workspace_id = uuid4()
        placement = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            is_current=True,
            status="DRAFT",
            metadata_json={"template_was_active_at_preview": False},
        )
        session = _ApprovalSession(placement, None)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]

        with self.assertRaises(AffiliateCommentError) as raised:
            service.approve_and_enqueue(placement.id, workspace_id, "operator@example.com")

        self.assertEqual(raised.exception.code, "affiliate_comment_template_test_only")

    def test_approval_blocks_a_missing_required_image(self) -> None:
        workspace_id = uuid4()
        placement = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            is_current=True,
            status="DRAFT",
            metadata_json={"template_was_active_at_preview": True},
            affiliate_url="https://example.com/affiliate-product",
            comment_message="CTA\nhttps://example.com/affiliate-product",
            attach_product_image=True,
            attachment_image_url=None,
        )
        session = _ApprovalSession(placement, None)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]

        with self.assertRaises(AffiliateCommentError) as raised:
            service.approve_and_enqueue(placement.id, workspace_id, "operator@example.com")

        self.assertEqual(raised.exception.code, "affiliate_comment_image_required")

    def test_approval_blocks_a_comment_that_removed_the_locked_affiliate_url(self) -> None:
        workspace_id = uuid4()
        placement = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            is_current=True,
            status="DRAFT",
            metadata_json={"template_was_active_at_preview": True},
            affiliate_url="https://example.com/affiliate-product",
            comment_message="Comment custom nhưng đã xóa link bắt buộc",
            attach_product_image=False,
            attachment_image_url=None,
        )
        session = _ApprovalSession(placement, None)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]

        with self.assertRaises(AffiliateCommentError) as raised:
            service.approve_and_enqueue(placement.id, workspace_id, "operator@example.com")

        self.assertEqual(raised.exception.code, "affiliate_comment_url_missing")

    def test_approval_after_terminal_job_uses_a_new_retry_idempotency_key(self) -> None:
        workspace_id = uuid4()
        publication_id = uuid4()
        placement = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            platform_publication_id=publication_id,
            affiliate_product_match_id=uuid4(),
            growth_assessment_id=uuid4(),
            message_sha256="b" * 64,
            comment_message="CTA\nhttps://example.com/affiliate-product",
            affiliate_url="https://example.com/affiliate-product",
            attach_product_image=False,
            attachment_image_url=None,
            is_current=True,
            status="FAILED",
            post_job_id=None,
            approved_at=None,
            metadata_json={},
        )
        terminal_job = SimpleNamespace(id=uuid4(), workspace_id=workspace_id, status=JobStatus.FAILED)
        placement.post_job_id = terminal_job.id
        session = _ApprovalSession(placement, terminal_job)
        service = AffiliateCommentService(session)  # type: ignore[arg-type]
        publication = SimpleNamespace(id=publication_id, source_video_id=uuid4(), affiliate_comment_status=None)
        service._load_context = lambda *_args: {  # type: ignore[method-assign]
            "publication": publication,
            "account": SimpleNamespace(id=uuid4()),
            "product_match": SimpleNamespace(id=placement.affiliate_product_match_id),
            "assessment": SimpleNamespace(id=placement.growth_assessment_id),
        }
        service._validate_gates = lambda _context: None  # type: ignore[method-assign]
        service.accounts.resolve_config = lambda _account_id: SimpleNamespace()  # type: ignore[method-assign]
        created_job = SimpleNamespace(id=uuid4(), status=JobStatus.QUEUED)
        captured = {}

        class _FakeJobService:
            def __init__(self, _db):
                pass

            def create_job(self, **kwargs):
                captured.update(kwargs)
                return created_job

        module = __import__(
            "src.affiliate_intelligence.services.affiliate_comment_service",
            fromlist=["JobService"],
        )
        original = module.JobService
        module.JobService = _FakeJobService
        try:
            updated, job, reused = service.approve_and_enqueue(placement.id, workspace_id, "operator@example.com")
        finally:
            module.JobService = original

        base_key = f"affiliate-comment-post:{placement.id}:{placement.message_sha256[:24]}"
        self.assertFalse(reused)
        self.assertIs(job, created_job)
        self.assertRegex(captured["idempotency_key"], rf"^{base_key}:retry:[0-9a-f]{{12}}$")
        self.assertEqual(updated.post_job_id, created_job.id)
        self.assertEqual(updated.status, "QUEUED")

    def test_comment_routes_are_registered(self) -> None:
        from src.main import app

        paths = app.openapi()["paths"]
        self.assertIn("/platform-publications/{publication_id}/affiliate-comment-placement/preview", paths)
        self.assertIn("/affiliate-comment-placements/{placement_id}/approve", paths)
        self.assertIn("/affiliate-comment-placements/{placement_id}/verification-jobs", paths)


if __name__ == "__main__":
    unittest.main()
