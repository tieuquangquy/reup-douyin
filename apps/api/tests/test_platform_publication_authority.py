from datetime import UTC, datetime
from types import MethodType, SimpleNamespace
import unittest
from uuid import uuid4

from src.enums import ExternalPublicationStatus, JobType, PlatformAccountStatus, PublishAttemptStatus, PublishTargetPlatform
from src.models.jobs import Job
from src.models.media import RenderOutput
from src.models.publish import PlatformAccount, PlatformPublication, PublishAttempt, PublishDraft
from src.publish.services.platform_publication_service import PlatformPublicationService
from src.publish.services.publish_attempt_service import PublishAttemptService
from src.publish.services.publish_lifecycle_service import PublishLifecycleService
from src.schemas.publish import ExistingFacebookReelRegisterRequest, PublishDraftPublishRequest


class _ScalarRows:
    def __init__(self, rows):
        self.rows = list(rows)

    def __iter__(self):
        return iter(self.rows)


class _PublicationSession:
    def __init__(self, draft, attempts, render):
        self.draft = draft
        self.attempts = attempts
        self.render = render
        self.publications: list[PlatformPublication] = []

    def get(self, model, object_id):
        if model is PublishDraft and object_id == self.draft.id:
            return self.draft
        if model is RenderOutput and object_id == self.render.id:
            return self.render
        return None

    def scalars(self, statement):
        sql = str(statement)
        if "FROM publish_attempts" in sql:
            return _ScalarRows(self.attempts)
        if "FROM platform_publications" in sql:
            return _ScalarRows(self.publications)
        raise AssertionError(sql)

    def scalar(self, statement):
        sql = str(statement)
        if "count(" in sql:
            return len(self.publications)
        if "FROM platform_publications" in sql:
            return None
        raise AssertionError(sql)

    def add(self, row):
        if isinstance(row, PlatformPublication) and row not in self.publications:
            self.publications.append(row)

    def flush(self):
        return None


class _EnqueueSession:
    def __init__(self):
        self.added = []

    def scalar(self, _statement):
        return None

    def add(self, row):
        self.added.append(row)

    def flush(self):
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = uuid4()

    def commit(self):
        return None

    def rollback(self):
        return None

    def refresh(self, _row):
        return None


class _ManualImportSession:
    def __init__(self, draft, account):
        self.draft = draft
        self.account = account
        self.attempts: list[PublishAttempt] = []
        self.publications: list[PlatformPublication] = []

    def get(self, model, object_id):
        if model is PublishDraft and object_id == self.draft.id:
            return self.draft
        if model is PlatformAccount and object_id == self.account.id:
            return self.account
        if model is RenderOutput:
            return None
        return None

    def scalar(self, statement):
        sql = str(statement)
        if "max(publish_attempts.attempt_number)" in sql:
            return max((item.attempt_number for item in self.attempts), default=0)
        if "FROM platform_publications" in sql:
            return self.publications[0] if self.publications else None
        raise AssertionError(sql)

    def scalars(self, statement):
        sql = str(statement)
        if "FROM publish_attempts" in sql:
            return _ScalarRows(sorted(self.attempts, key=lambda item: item.attempt_number, reverse=True))
        if "FROM platform_publications" in sql:
            return _ScalarRows(self.publications)
        raise AssertionError(sql)

    def add(self, row):
        if isinstance(row, PublishAttempt):
            self.attempts.append(row)
        if isinstance(row, PlatformPublication):
            self.publications.append(row)

    def flush(self):
        now = datetime.now(UTC)
        for row in [*self.attempts, *self.publications]:
            if getattr(row, "id", None) is None:
                row.id = uuid4()
            if getattr(row, "created_at", None) is None:
                row.created_at = now
            if getattr(row, "updated_at", None) is None:
                row.updated_at = now

    def commit(self):
        return None

    def rollback(self):
        return None

    def refresh(self, _row):
        return None


def _attempt(*, number: int, external_id: str):
    now = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid4(),
        attempt_number=number,
        platform=PublishTargetPlatform.FACEBOOK_REELS,
        platform_account_id=uuid4(),
        external_publish_id=external_id,
        external_media_id=external_id,
        external_reel_id=external_id,
        external_permalink=f"https://facebook.com/reel/{external_id}",
        external_status=ExternalPublicationStatus.PUBLISHED,
        last_status_checked_at=now,
        finished_at=now,
    )


class PlatformPublicationAuthorityTests(unittest.TestCase):
    def test_sync_is_idempotent_for_one_external_post(self) -> None:
        attempt = _attempt(number=1, external_id="reel-1")
        draft = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            source_video_id=uuid4(),
            render_output_id=uuid4(),
            canonical_publish_attempt_id=attempt.id,
        )
        render = SimpleNamespace(
            id=draft.render_output_id,
            media_asset=SimpleNamespace(checksum_sha256="a" * 64),
        )
        db = _PublicationSession(draft, [attempt], render)
        service = PlatformPublicationService(db)  # type: ignore[arg-type]

        first = service.sync_for_draft(draft.id)
        second = service.sync_for_draft(draft.id)

        self.assertIs(first, second)
        self.assertEqual(len(db.publications), 1)
        self.assertTrue(first.is_canonical)
        self.assertEqual(first.external_publish_id, "reel-1")
        self.assertEqual(first.content_fingerprint_sha256, "a" * 64)

    def test_duplicate_real_posts_are_retained_but_only_one_is_canonical(self) -> None:
        first_attempt = _attempt(number=1, external_id="reel-1")
        second_attempt = _attempt(number=2, external_id="reel-2")
        second_attempt.platform_account_id = first_attempt.platform_account_id
        draft = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            source_video_id=uuid4(),
            render_output_id=uuid4(),
            canonical_publish_attempt_id=second_attempt.id,
        )
        render = SimpleNamespace(id=draft.render_output_id, media_asset=SimpleNamespace(checksum_sha256=None))
        db = _PublicationSession(draft, [first_attempt, second_attempt], render)

        canonical = PlatformPublicationService(db).sync_for_draft(draft.id)  # type: ignore[arg-type]

        self.assertEqual(len(db.publications), 2)
        self.assertEqual(canonical.external_publish_id, "reel-2")
        self.assertEqual(sum(1 for row in db.publications if row.is_canonical), 1)

    def test_enqueue_creates_attempt_and_single_attempt_worker_job(self) -> None:
        db = _EnqueueSession()
        service = object.__new__(PublishAttemptService)
        service.db = db
        service.lifecycle = SimpleNamespace()
        service.publications = SimpleNamespace()
        service.storage = SimpleNamespace()
        service.connector = SimpleNamespace()

        draft = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), source_video_id=uuid4(), target_platform="FACEBOOK_REELS")
        render = SimpleNamespace(id=uuid4())
        account = SimpleNamespace(id=uuid4(), platform=PublishTargetPlatform.FACEBOOK_REELS)
        gate = SimpleNamespace(warnings=[])

        def _validate(_self, _draft_id, _request):
            return draft, render, account, gate

        service._validate_publish_request = MethodType(_validate, service)
        service._sync_draft = MethodType(lambda _self, _draft: None, service)

        attempt = service.enqueue_publish(
            draft.id,
            PublishDraftPublishRequest(platform_account_id=account.id),
        )

        jobs = [row for row in db.added if isinstance(row, Job)]
        self.assertEqual(attempt.status, PublishAttemptStatus.QUEUED)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].job_type, JobType.PUBLISH_CONTENT)
        self.assertEqual(jobs[0].max_attempts, 1)
        self.assertEqual(jobs[0].payload_json["publish_attempt_id"], str(attempt.id))
        self.assertEqual(attempt.created_by_job_id, jobs[0].id)
        self.assertNotIn("video_path", attempt.request_summary_json)

    def test_resumed_running_attempt_is_not_uploaded_again(self) -> None:
        db = _EnqueueSession()
        service = object.__new__(PublishAttemptService)
        service.db = db
        service.lifecycle = PublishLifecycleService(db)  # type: ignore[arg-type]
        service.publications = SimpleNamespace()
        service.storage = SimpleNamespace()
        service.connector = SimpleNamespace(publish=lambda *_args, **_kwargs: self.fail("must not publish"))

        draft = SimpleNamespace(id=uuid4())
        attempt = SimpleNamespace(
            id=uuid4(),
            publish_draft_id=draft.id,
            status=PublishAttemptStatus.RUNNING,
            external_publish_id=None,
            external_media_id=None,
            external_reel_id=None,
            reconciliation_required=False,
            reconciliation_status=None,
            error_code=None,
            error_message=None,
            finished_at=None,
        )
        service.get_attempt = MethodType(lambda _self, _attempt_id: attempt, service)
        service._get_draft = MethodType(lambda _self, _draft_id: draft, service)
        service._sync_draft = MethodType(lambda _self, _draft: None, service)

        result = service.execute_attempt(attempt.id)

        self.assertIs(result, attempt)
        self.assertEqual(attempt.status, PublishAttemptStatus.FAILED)
        self.assertEqual(attempt.error_code, "publish_attempt_resume_requires_operator_check")

    def test_manual_import_is_idempotent_and_never_calls_external_network(self) -> None:
        now = datetime.now(UTC)
        workspace_id = uuid4()
        draft = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            source_video_id=uuid4(),
            render_output_id=None,
            target_platform="FACEBOOK_REELS",
            status="READY",
            latest_publish_attempt_id=None,
            canonical_publish_attempt_id=None,
            current_publication_status=ExternalPublicationStatus.UNKNOWN,
            current_external_publish_id=None,
            current_external_permalink=None,
            published_at=None,
            last_publish_synced_at=None,
            publication_summary_json=None,
            error_message=None,
            updated_at=now,
        )
        account = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            status=PlatformAccountStatus.ACTIVE,
            is_on_hold=False,
            cooldown_until=None,
        )
        db = _ManualImportSession(draft, account)
        service = PlatformPublicationService(db)  # type: ignore[arg-type]
        request = ExistingFacebookReelRegisterRequest(
            publish_draft_id=draft.id,
            platform_account_id=account.id,
            external_publish_id="page_987654321098765",
            external_reel_id="987654321098765",
            external_permalink="https://www.facebook.com/reel/987654321098765",
            published_at=now,
            operator_attestation="EXISTING_FACEBOOK_REEL_VERIFIED",
        )

        first = service.register_existing_facebook_reel(request)
        second = service.register_existing_facebook_reel(request)

        self.assertIs(first, second)
        self.assertEqual(first.origin, "MANUAL_IMPORT")
        self.assertEqual(first.status, ExternalPublicationStatus.PUBLISHED)
        self.assertTrue(first.is_canonical)
        self.assertEqual(len(db.attempts), 1)
        self.assertEqual(db.attempts[0].metadata_json["publication_origin"], "MANUAL_IMPORT")
        self.assertFalse(db.attempts[0].response_summary_json["external_network_called"])


if __name__ == "__main__":
    unittest.main()
