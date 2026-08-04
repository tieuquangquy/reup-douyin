from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.affiliate import AffiliateProductImageAsset
from src.models.publish import PlatformIntegrationConfiguration
from src.storage.local import LocalStorageBackend


MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class AffiliateProductImageError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AffiliateProductImageService:
    def __init__(self, db: Session):
        self.db = db
        self.storage = LocalStorageBackend(get_settings().local_storage_root)

    def upload(
        self,
        workspace_id: UUID,
        *,
        content: bytes,
        original_filename: str | None,
        declared_content_type: str | None,
        uploaded_by: str,
    ) -> AffiliateProductImageAsset:
        if not content:
            raise AffiliateProductImageError("affiliate_image_empty", "The uploaded image is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise AffiliateProductImageError("affiliate_image_too_large", "Images must be 8 MB or smaller")
        if declared_content_type and declared_content_type.lower() not in ALLOWED_CONTENT_TYPES:
            raise AffiliateProductImageError(
                "affiliate_image_type_invalid",
                "Only JPEG, PNG, and WebP images are supported",
            )

        normalized = self._normalize_image(content)
        checksum = sha256(normalized).hexdigest()
        existing = self.db.scalar(
            select(AffiliateProductImageAsset).where(
                AffiliateProductImageAsset.workspace_id == workspace_id,
                AffiliateProductImageAsset.checksum_sha256 == checksum,
                AffiliateProductImageAsset.is_active.is_(True),
            )
        )
        if existing is not None:
            return existing

        storage_key = f"affiliate-product-images/{workspace_id}/{checksum}.jpg"
        self.storage.write_bytes(storage_key, normalized)
        asset = AffiliateProductImageAsset(
            workspace_id=workspace_id,
            storage_provider=self.storage.provider_name,
            storage_key=storage_key,
            original_filename=self._safe_filename(original_filename),
            content_type="image/jpeg",
            size_bytes=len(normalized),
            checksum_sha256=checksum,
            uploaded_by=uploaded_by[:180],
            is_active=True,
            metadata_json={"source": "OPERATOR_UPLOAD", "normalized_format": "JPEG"},
        )
        self.db.add(asset)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            concurrent = self.db.scalar(
                select(AffiliateProductImageAsset).where(
                    AffiliateProductImageAsset.workspace_id == workspace_id,
                    AffiliateProductImageAsset.checksum_sha256 == checksum,
                    AffiliateProductImageAsset.is_active.is_(True),
                )
            )
            if concurrent is None:
                raise
            return concurrent
        self.db.refresh(asset)
        return asset

    def get_public(self, asset_id: UUID) -> AffiliateProductImageAsset | None:
        return self.db.scalar(
            select(AffiliateProductImageAsset).where(
                AffiliateProductImageAsset.id == asset_id,
                AffiliateProductImageAsset.is_active.is_(True),
            )
        )

    def configured_public_origin(self, workspace_id: UUID) -> str | None:
        configuration = self.db.scalar(
            select(PlatformIntegrationConfiguration).where(
                PlatformIntegrationConfiguration.workspace_id == workspace_id,
                PlatformIntegrationConfiguration.provider == "FACEBOOK",
                PlatformIntegrationConfiguration.enabled.is_(True),
            )
        )
        redirect_uri = str(configuration.oauth_redirect_uri if configuration else "").strip()
        parsed = urlsplit(redirect_uri)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            return None
        # Quick Tunnel hostnames are temporary. Persisting one into product data
        # makes local previews and later Meta fetches fail as soon as the tunnel
        # restarts. In that case the route falls back to the current request
        # origin; only a named/custom HTTPS tunnel is treated as stable config.
        hostname = str(parsed.hostname or "").lower()
        if hostname.endswith(".trycloudflare.com"):
            return None
        return f"https://{parsed.netloc}"

    @staticmethod
    def _normalize_image(content: bytes) -> bytes:
        try:
            with Image.open(BytesIO(content)) as probe:
                probe.verify()
            with Image.open(BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise AffiliateProductImageError(
                "affiliate_image_invalid",
                "The uploaded file is not a valid image",
            ) from exc
        if image.width < 1 or image.height < 1:
            raise AffiliateProductImageError("affiliate_image_invalid", "The uploaded image has no visible dimensions")
        if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
            image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
        return output.getvalue()

    @staticmethod
    def _safe_filename(filename: str | None) -> str | None:
        if not filename:
            return None
        name = Path(filename).name
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
        return name[:240] or None
