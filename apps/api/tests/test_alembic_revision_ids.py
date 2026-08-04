from __future__ import annotations

import unittest

from alembic.config import Config
from alembic.script import ScriptDirectory


class AlembicRevisionIdTests(unittest.TestCase):
    def test_revision_ids_fit_default_alembic_version_column(self) -> None:
        revisions = list(ScriptDirectory.from_config(Config("alembic.ini")).walk_revisions())

        self.assertTrue(revisions)
        for revision in revisions:
            with self.subTest(revision=revision.revision):
                self.assertLessEqual(
                    len(revision.revision),
                    32,
                    "Alembic's default version_num column is VARCHAR(32)",
                )


if __name__ == "__main__":
    unittest.main()
