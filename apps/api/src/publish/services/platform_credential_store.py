from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.settings import Settings
from src.models.publish import PlatformAccount, PlatformCredential
from src.publish.services.platform_credential_key_store import resolve_platform_credential_key_ref
from src.publish.services.platform_secret_envelope import PlatformSecretEnvelope


PLATFORM_CREDENTIAL_REFERENCE_PREFIX = "platform-credential://"


class PlatformCredentialStore:
    """Database-backed local credential adapter with an opaque public reference."""

    def __init__(self, db: Session, *, settings: Settings):
        self.db = db
        self.envelope = PlatformSecretEnvelope(
            key_ref=resolve_platform_credential_key_ref(settings)
        )

    @property
    def configured(self) -> bool:
        return self.envelope.configured

    def store_facebook_page_token(
        self,
        account: PlatformAccount,
        token: str,
        *,
        metadata: dict | None = None,
    ) -> PlatformCredential:
        credential = self.db.scalar(
            select(PlatformCredential).where(
                PlatformCredential.platform_account_id == account.id,
                PlatformCredential.provider == "FACEBOOK",
                PlatformCredential.credential_kind == "PAGE_ACCESS_TOKEN",
            )
        )
        if credential is None:
            credential = PlatformCredential(
                id=uuid4(),
                workspace_id=account.workspace_id,
                platform_account_id=account.id,
                provider="FACEBOOK",
                credential_kind="PAGE_ACCESS_TOKEN",
                encrypted_value="pending",
                key_version="envelope-v1",
            )
            self.db.add(credential)

        credential.encrypted_value = self.envelope.encrypt(
            token,
            context=self._context(credential),
        )
        credential.last_validated_at = datetime.now(UTC)
        credential.metadata_json = {
            **(credential.metadata_json or {}),
            **(metadata or {}),
            "secret_exposed_to_browser": False,
        }
        account.token_reference = self.reference_for(credential.id)
        return credential

    def resolve(self, reference: str, *, account: PlatformAccount) -> str | None:
        credential_id = self.parse_reference(reference)
        if credential_id is None:
            return None
        credential = self.db.get(PlatformCredential, credential_id)
        if (
            credential is None
            or credential.workspace_id != account.workspace_id
            or credential.platform_account_id != account.id
            or credential.provider != "FACEBOOK"
            or credential.credential_kind != "PAGE_ACCESS_TOKEN"
        ):
            return None
        return self.envelope.decrypt(
            credential.encrypted_value,
            context=self._context(credential),
        )

    @staticmethod
    def reference_for(credential_id: UUID) -> str:
        return f"{PLATFORM_CREDENTIAL_REFERENCE_PREFIX}{credential_id}"

    @staticmethod
    def parse_reference(reference: str) -> UUID | None:
        if not reference.startswith(PLATFORM_CREDENTIAL_REFERENCE_PREFIX):
            return None
        try:
            return UUID(reference.removeprefix(PLATFORM_CREDENTIAL_REFERENCE_PREFIX))
        except ValueError:
            return None

    @staticmethod
    def _context(credential: PlatformCredential) -> str:
        return (
            f"platform-credential:{credential.id}:"
            f"{credential.workspace_id}:{credential.platform_account_id}:"
            f"{credential.provider}:{credential.credential_kind}"
        )
