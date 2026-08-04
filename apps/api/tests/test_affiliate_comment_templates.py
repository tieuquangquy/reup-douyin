from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.affiliate_intelligence.services.affiliate_comment_template_service import (
    AffiliateCommentTemplateError,
    AffiliateCommentTemplateService,
)
from src.main import create_app


class AffiliateCommentTemplateTests(unittest.TestCase):
    def test_template_render_replaces_description_and_hides_image_token(self) -> None:
        rendered = AffiliateCommentTemplateService.render(
            "{{cta}}\n{{product_name}}\n{{description}}\n{{product_image}}\n{{affiliate_url}}\n{{disclosure}}",
            {
                "cta": "Xem sản phẩm",
                "product_name": "Trà thảo mộc",
                "description": "Hương vị tự nhiên.",
                "product_image": "",
                "affiliate_url": "https://example.com/tea",
                "disclosure": "Tôi có thể nhận hoa hồng.",
            },
        )
        self.assertEqual(
            rendered,
            "Xem sản phẩm\nTrà thảo mộc\nHương vị tự nhiên.\n\nhttps://example.com/tea\nTôi có thể nhận hoa hồng.",
        )

    def test_template_validation_rejects_unknown_and_missing_required_variables(self) -> None:
        with self.assertRaises(AffiliateCommentTemplateError) as unknown:
            AffiliateCommentTemplateService.validate_template("{{product_name}} {{unknown}}")
        self.assertEqual(unknown.exception.code, "affiliate_comment_template_variable_invalid")
        with self.assertRaises(AffiliateCommentTemplateError) as missing:
            AffiliateCommentTemplateService.validate_template("{{product_name}} {{cta}}")
        self.assertEqual(missing.exception.code, "affiliate_comment_template_variable_required")

    def test_disclosure_variable_is_optional(self) -> None:
        AffiliateCommentTemplateService.validate_template("{{cta}}\n{{product_name}}\n{{affiliate_url}}")

    def test_custom_item_template_allows_supported_variables_without_mutating_shared_requirements(self) -> None:
        AffiliateCommentTemplateService.validate_custom_template("Tự viết {{product_name}} {{affiliate_url}} {{product_image}}")
        with self.assertRaises(AffiliateCommentTemplateError) as unknown:
            AffiliateCommentTemplateService.validate_custom_template("{{affiliate_url}} {{unsupported}}")
        self.assertEqual(unknown.exception.code, "affiliate_comment_template_variable_invalid")

    def test_template_routes_are_registered(self) -> None:
        paths = TestClient(create_app()).get("/openapi.json").json()["paths"]
        self.assertIn("/affiliate-comment-templates", paths)
        self.assertIn("/affiliate-comment-templates/{template_id}", paths)
        self.assertIn("/affiliate-comment-templates/{template_id}/activate", paths)
        self.assertIn("/platform-publications/{publication_id}/affiliate-comment-placements", paths)
        self.assertIn("delete", paths["/affiliate-comment-templates/{template_id}"])


if __name__ == "__main__":
    unittest.main()
