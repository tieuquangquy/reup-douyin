from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address
import socket
from urllib.parse import urljoin, urlparse
from uuid import UUID

import requests
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from src.enums import JobStatus, JobType
from src.models.affiliate import AffiliateCommentPlacement
from src.models.jobs import Job
from src.models.publish import PlatformAccount
from src.publish.connectors.base import PublishConnectorError
from src.publish.connectors.facebook_reels import FacebookReelsConnector
from src.publish.services.platform_account_service import PlatformAccountError, PlatformAccountService
from src.services.job_service import JobService


class AffiliateCommentVerificationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AffiliateCommentVerificationService:
    def __init__(self, db: Session):
        self.db = db
        self.accounts = PlatformAccountService(db)

    def enqueue(
        self,
        placement_id: UUID,
        workspace_id: UUID,
        *,
        mode: str = "manual",
        scheduled_at: datetime | None = None,
    ) -> tuple[AffiliateCommentPlacement, Job, bool]:
        placement = self.db.get(AffiliateCommentPlacement, placement_id)
        if placement is None or placement.workspace_id != workspace_id:
            raise AffiliateCommentVerificationError("affiliate_comment_not_found", "Affiliate comment placement was not found")
        if placement.status != "POSTED" or not placement.external_comment_id:
            raise AffiliateCommentVerificationError("affiliate_comment_not_posted", "Only a posted comment can be verified")

        if mode == "manual":
            existing = self.db.scalar(
                select(Job)
                .where(
                    Job.workspace_id == workspace_id,
                    Job.reference_type == "affiliate_comment_placement",
                    Job.reference_id == placement.id,
                    Job.job_type == JobType.VERIFY_AFFILIATE_COMMENT,
                    Job.idempotency_key.like(f"affiliate-comment-verify:{placement.id}:manual:%"),
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYABLE]),
                )
                .order_by(Job.created_at.desc())
            )
            if existing is not None:
                return placement, existing, True
            key = f"affiliate-comment-verify:{placement.id}:manual:{datetime.now(UTC).timestamp()}"
        else:
            key = f"affiliate-comment-verify:{placement.id}:{mode}"
            existing = self.db.scalar(select(Job).where(Job.workspace_id == workspace_id, Job.idempotency_key == key))
            if existing is not None:
                return placement, existing, True

        try:
            job = JobService(self.db).create_job(
                workspace_id=workspace_id,
                job_type=JobType.VERIFY_AFFILIATE_COMMENT,
                reference_type="affiliate_comment_placement",
                reference_id=placement.id,
                idempotency_key=key,
                max_attempts=2,
                scheduled_at=scheduled_at,
                payload_json={"affiliate_comment_placement_id": str(placement.id), "mode": mode},
            )
        except DBAPIError as exc:
            self.db.rollback()
            database_error = str(getattr(exc, "orig", exc))
            if "VERIFY_AFFILIATE_COMMENT" in database_error or "job_type" in database_error:
                raise AffiliateCommentVerificationError(
                    "affiliate_comment_verification_setup_incomplete",
                    "Database migration 0051 is required before comment verification can run",
                ) from exc
            raise
        return placement, job, False

    def execute_job(self, job_id: UUID) -> AffiliateCommentPlacement:
        job = JobService(self.db).get_job(job_id)
        if job.job_type != JobType.VERIFY_AFFILIATE_COMMENT:
            raise AffiliateCommentVerificationError("affiliate_comment_verification_job_type_invalid", "Job is not a comment verification job")
        placement_id = UUID(str((job.payload_json or {}).get("affiliate_comment_placement_id") or ""))
        placement = self.db.get(AffiliateCommentPlacement, placement_id)
        if placement is None or placement.workspace_id != job.workspace_id:
            raise AffiliateCommentVerificationError("affiliate_comment_not_found", "Affiliate comment placement was not found")
        if placement.status != "POSTED" or not placement.external_comment_id:
            raise AffiliateCommentVerificationError("affiliate_comment_not_posted", "Only a posted comment can be verified")

        account = self.db.get(PlatformAccount, placement.platform_account_id)
        if account is None or account.workspace_id != job.workspace_id:
            raise AffiliateCommentVerificationError("affiliate_comment_account_not_found", "Facebook Page account was not found")
        try:
            config = self.accounts.resolve_config(account.id, require_active=False)
        except PlatformAccountError as exc:
            raise AffiliateCommentVerificationError("affiliate_comment_credential_unavailable", str(exc)) from exc

        try:
            comment = FacebookReelsConnector().verify_affiliate_comment(
                account=config,
                external_comment_id=placement.external_comment_id,
            )
        except PublishConnectorError as exc:
            raise AffiliateCommentVerificationError(exc.code, str(exc)) from exc

        expected = " ".join(str(placement.comment_message or "").split())
        actual = " ".join(str(comment.get("message") or "").split())
        message_matches = bool(actual) and actual == expected
        comment_status = str(comment.get("status") or "CHECK_FAILED")
        if comment_status == "VERIFIED" and not message_matches:
            comment_status = "CONTENT_MISMATCH"
        if placement.attach_product_image:
            # Graph can omit attachment fields for a visible photo comment. Treat absence as
            # unconfirmed instead of falsely declaring that the image disappeared.
            attachment_status = "VERIFIED" if comment.get("has_attachment") else "UNCONFIRMED"
        else:
            attachment_status = "NOT_EXPECTED"

        try:
            link = check_affiliate_url(placement.affiliate_url)
        except AffiliateCommentVerificationError as exc:
            link = {
                "status": "UNSAFE_REDIRECT" if exc.code == "affiliate_link_unsafe_redirect" else "CHECK_FAILED",
                "error_code": exc.code,
                "status_code": None,
                "redirect_count": 0,
            }
        if comment_status == "VERIFIED" and placement.attach_product_image and attachment_status != "VERIFIED":
            overall = "CHECK_FAILED"
        elif comment_status == "VERIFIED" and link["status"] == "HEALTHY":
            overall = "VERIFIED"
        elif comment_status in {"HIDDEN", "NOT_FOUND", "CONTENT_MISMATCH"} or link["status"] in {"BROKEN", "UNSAFE_REDIRECT"}:
            overall = "NEEDS_ATTENTION"
        else:
            overall = "CHECK_FAILED"
        verification = {
            "status": overall,
            "checked_at": datetime.now(UTC).isoformat(),
            "job_id": str(job.id),
            "comment": {
                "status": comment_status,
                "message_matches": message_matches,
                "attachment_status": attachment_status,
            },
            "link": link,
        }
        metadata = dict(placement.metadata_json or {})
        metadata["verification"] = verification
        placement.metadata_json = metadata
        self.db.commit()
        self.db.refresh(placement)
        return placement


def _resolve_public_addresses(hostname: str) -> None:
    try:
        addresses = {ip_address(item[4][0]) for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise AffiliateCommentVerificationError("affiliate_link_dns_failed", "Affiliate URL host could not be resolved") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise AffiliateCommentVerificationError("affiliate_link_unsafe_redirect", "Affiliate URL resolves to a private or local network")


def _validate_public_url(value: str) -> str:
    parsed = urlparse(value)
    hostname = str(parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not hostname or parsed.username or parsed.password or hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise AffiliateCommentVerificationError("affiliate_link_unsafe_redirect", "Affiliate URL must use public HTTPS")
    try:
        address = ip_address(hostname)
    except ValueError:
        _resolve_public_addresses(hostname)
    else:
        if not address.is_global:
            raise AffiliateCommentVerificationError("affiliate_link_unsafe_redirect", "Affiliate URL resolves to a private or local network")
    return value


def check_affiliate_url(value: str) -> dict:
    current = _validate_public_url(str(value or "").strip())
    redirects = 0
    status_code: int | None = None
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "reup-douyin/affiliate-link-check"})
    try:
        for _ in range(5):
            response = session.head(current, allow_redirects=False, timeout=(5, 15))
            if response.status_code in {405, 501}:
                response = session.get(current, allow_redirects=False, timeout=(5, 15), stream=True)
            status_code = int(response.status_code)
            if status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    return {"status": "TEMPORARY_FAILURE", "status_code": status_code, "redirect_count": redirects}
                current = _validate_public_url(urljoin(current, location))
                redirects += 1
                continue
            parsed = urlparse(current)
            if status_code in {401, 403}:
                health = "ACCESS_RESTRICTED"
            elif status_code == 429:
                health = "RATE_LIMITED"
            elif status_code in {404, 410}:
                health = "BROKEN"
            elif 200 <= status_code < 400:
                health = "HEALTHY"
            elif status_code >= 500:
                health = "TEMPORARY_FAILURE"
            else:
                health = "CHECK_FAILED"
            return {"status": health, "status_code": status_code, "final_domain": parsed.hostname, "redirect_count": redirects}
        return {"status": "UNSAFE_REDIRECT", "status_code": status_code, "redirect_count": redirects}
    except AffiliateCommentVerificationError:
        raise
    except requests.Timeout:
        return {"status": "TEMPORARY_FAILURE", "status_code": status_code, "redirect_count": redirects}
    except requests.RequestException:
        return {"status": "CHECK_FAILED", "status_code": status_code, "redirect_count": redirects}
    finally:
        session.close()
