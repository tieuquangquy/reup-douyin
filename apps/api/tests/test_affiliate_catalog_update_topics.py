"""Affiliate catalog PATCH: topic remap must not 500 on overlapping unique mappings."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from src.affiliate_intelligence.services.affiliate_product_service import (
    AffiliateCatalogService,
    AffiliateIntelligenceError,
)
from src.schemas.affiliate import AffiliateProductUpdateRequest


class AffiliateCatalogUpdateTopicsTests(unittest.TestCase):
    def test_apply_topic_ids_keeps_overlap_and_flushes_removals_before_inserts(self) -> None:
        workspace_id = uuid4()
        kept_topic_id = uuid4()
        removed_topic_id = uuid4()
        added_topic_id = uuid4()
        events: list[str] = []
        kept_mapping = SimpleNamespace(topic_category_id=kept_topic_id)
        removed_mapping = SimpleNamespace(topic_category_id=removed_topic_id)

        class TrackingMappings(list):
            def remove(self, item: object) -> None:
                events.append("remove")
                super().remove(item)

            def append(self, item: object) -> None:
                events.append("append")
                super().append(item)

            def clear(self) -> None:  # pragma: no cover - must not be used for remap
                events.append("clear")
                super().clear()

        product = SimpleNamespace(
            name="test2",
            affiliate_url="https://s.shopee.vn/example",
            platform="TIKTOK_SHOP",
            external_product_id="124214",
            metadata_json={"source": "OPERATOR"},
            topic_mappings=TrackingMappings([kept_mapping, removed_mapping]),
        )
        topics = [
            SimpleNamespace(id=kept_topic_id),
            SimpleNamespace(id=added_topic_id),
        ]
        service = object.__new__(AffiliateCatalogService)
        service.db = SimpleNamespace(
            flush=lambda: events.append("flush"),
            scalars=lambda _statement: topics,
        )

        service._apply(  # type: ignore[attr-defined]
            product,
            workspace_id,
            {"topic_ids": [kept_topic_id, added_topic_id]},
            creating=False,
        )

        self.assertNotIn("clear", events, "Remap must not wipe and recreate kept topic rows")
        self.assertEqual(events[:3], ["remove", "flush", "append"])
        self.assertEqual(
            [mapping.topic_category_id for mapping in product.topic_mappings],
            [kept_topic_id, added_topic_id],
        )
        self.assertIs(product.topic_mappings[0], kept_mapping)

    def test_update_maps_integrity_error_to_domain_error(self) -> None:
        workspace_id = uuid4()
        product_id = uuid4()
        product = SimpleNamespace(id=product_id, fingerprint_sha256="abc123")
        rolled_back: list[str] = []
        service = object.__new__(AffiliateCatalogService)
        service.get = lambda _workspace, _product: product  # type: ignore[method-assign]
        service._apply = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        service.db = SimpleNamespace(
            scalar=lambda _statement: None,
            commit=lambda: (_ for _ in ()).throw(
                IntegrityError("UPDATE affiliate_products", {}, Exception("duplicate key"))
            ),
            rollback=lambda: rolled_back.append("rollback"),
        )

        with self.assertRaises(AffiliateIntelligenceError) as context:
            service.update(  # type: ignore[attr-defined]
                workspace_id,
                product_id,
                AffiliateProductUpdateRequest(name="test2"),
            )

        self.assertEqual(context.exception.code, "affiliate_product_exists")
        self.assertEqual(rolled_back, ["rollback"])


if __name__ == "__main__":
    unittest.main()
