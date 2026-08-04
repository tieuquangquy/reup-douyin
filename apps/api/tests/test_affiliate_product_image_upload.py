from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from src.affiliate_intelligence.services.affiliate_product_image_service import (
    MAX_UPLOAD_BYTES,
    AffiliateProductImageError,
    AffiliateProductImageService,
)
from src.affiliate_intelligence.services.affiliate_product_service import AffiliateCatalogService
from src.main import create_app


def _png_bytes(size: tuple[int, int] = (4, 3)) -> bytes:
    image = Image.new("RGBA", size, (20, 120, 80, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class AffiliateProductImageUploadTests(unittest.TestCase):
    def test_valid_png_is_normalized_to_sanitized_jpeg(self) -> None:
        normalized = AffiliateProductImageService._normalize_image(_png_bytes())

        with Image.open(BytesIO(normalized)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (4, 3))

    def test_invalid_bytes_are_rejected(self) -> None:
        with self.assertRaises(AffiliateProductImageError) as context:
            AffiliateProductImageService._normalize_image(b"not-an-image")
        self.assertEqual(context.exception.code, "affiliate_image_invalid")

    def test_upload_rejects_content_over_limit_before_storage(self) -> None:
        service = AffiliateProductImageService(None)  # type: ignore[arg-type]

        with self.assertRaises(AffiliateProductImageError) as context:
            service.upload(
                workspace_id=uuid4(),
                content=b"x" * (MAX_UPLOAD_BYTES + 1),
                original_filename="too-large.png",
                declared_content_type="image/png",
                uploaded_by="operator",
            )
        self.assertEqual(context.exception.code, "affiliate_image_too_large")

    def test_filename_is_reduced_to_safe_basename(self) -> None:
        self.assertEqual(
            AffiliateProductImageService._safe_filename("folder/tea label?.png"),
            "tea_label_.png",
        )
        self.assertIsNone(AffiliateProductImageService._safe_filename("..."))

    def test_upload_and_public_routes_are_registered(self) -> None:
        client = TestClient(create_app())
        paths = client.get("/openapi.json").json()["paths"]

        self.assertIn("/affiliate-product-images", paths)
        self.assertIn("post", paths["/affiliate-product-images"])
        self.assertIn("/public/affiliate-product-images/{asset_id}", paths)
        self.assertIn("get", paths["/public/affiliate-product-images/{asset_id}"])

    def test_ephemeral_quick_tunnel_is_not_persisted_as_public_origin(self) -> None:
        service = object.__new__(AffiliateProductImageService)
        service.db = SimpleNamespace(  # type: ignore[assignment]
            scalar=lambda _statement: SimpleNamespace(
                oauth_redirect_uri="https://temporary-name.trycloudflare.com/publishing/accounts/facebook/callback"
            )
        )
        self.assertIsNone(service.configured_public_origin(uuid4()))

        service.db = SimpleNamespace(  # type: ignore[assignment]
            scalar=lambda _statement: SimpleNamespace(
                oauth_redirect_uri="https://publish.example.com/publishing/accounts/facebook/callback"
            )
        )
        self.assertEqual(service.configured_public_origin(uuid4()), "https://publish.example.com")

    def test_catalog_apply_persists_and_replaces_product_image_url(self) -> None:
        product = SimpleNamespace(
            name="Tea",
            affiliate_url="https://example.com/affiliate/tea",
            platform="SHOPEE",
            external_product_id="SKU-1",
            image_url="https://cdn.example.com/old.jpg",
        )
        service = object.__new__(AffiliateCatalogService)

        service._apply(  # type: ignore[attr-defined]
            product,
            uuid4(),
            {"image_url": "https://cdn.example.com/new.jpg"},
            creating=False,
        )

        self.assertEqual(product.image_url, "https://cdn.example.com/new.jpg")


if __name__ == "__main__":
    unittest.main()
