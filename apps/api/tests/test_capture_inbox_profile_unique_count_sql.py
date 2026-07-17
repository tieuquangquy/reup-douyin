from __future__ import annotations

import unittest

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects import postgresql

from src.models.capture_inbox import CapturedItem


class CaptureInboxProfileUniqueCountSqlTests(unittest.TestCase):
    def test_unique_video_count_query_uses_count_distinct_syntax(self) -> None:
        stmt = select(func.count(distinct(CapturedItem.source_video_external_id))).select_from(CapturedItem)
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        normalized = compiled.lower()
        self.assertIn("count(distinct captured_items.source_video_external_id)", normalized)
        self.assertNotIn("distinct(captured_items.source_video_external_id)", normalized)


if __name__ == "__main__":
    unittest.main()
