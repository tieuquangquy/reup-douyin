"""Delete Content AI prompt profiles without live network."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from src.content_intelligence.services.content_ai_settings_service import (
    CONTENT_PROMPT_SETTINGS_KEY,
    ContentAiSettingsError,
    ContentAiSettingsService,
)


def _profile(profile_id: str, name: str) -> dict:
    return {
        "id": profile_id,
        "name": name,
        "version": "CLASSIFICATION_PROMPT_V1",
        "prompt": "x" * 80,
    }


class ContentAiPromptDeleteTests(unittest.TestCase):
    def _service(self, *, active_id: str, profiles: list[dict]):
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                CONTENT_PROMPT_SETTINGS_KEY: {"active_profile_id": active_id, "profiles": profiles},
            },
        )

        def persist(_workspace, meta):
            workspace.settings_json = meta

        service = ContentAiSettingsService.__new__(ContentAiSettingsService)
        service.workspace_settings = SimpleNamespace(
            _resolve_workspace=lambda _workspace_id: workspace,
            _persist_workspace_settings=persist,
        )
        return service, workspace

    def test_deletes_non_active_profile_and_keeps_active(self) -> None:
        service, _workspace = self._service(
            active_id="keep",
            profiles=[_profile("keep", "Keep"), _profile("drop", "Drop")],
        )
        payload = service.delete_prompt(None, "drop")
        ids = [item["id"] for item in payload["prompts"]]
        self.assertEqual(ids, ["keep"])
        self.assertEqual(payload["active_prompt_id"], "keep")

    def test_deleting_active_profile_activates_remaining(self) -> None:
        service, _workspace = self._service(
            active_id="old",
            profiles=[_profile("old", "Old"), _profile("next", "Next")],
        )
        payload = service.delete_prompt(None, "old")
        self.assertEqual(payload["active_prompt_id"], "next")
        self.assertEqual([item["id"] for item in payload["prompts"]], ["next"])

    def test_refuses_to_delete_the_last_profile(self) -> None:
        service, _workspace = self._service(active_id="only", profiles=[_profile("only", "Only")])
        with self.assertRaisesRegex(ContentAiSettingsError, "prompt_last_remaining"):
            service.delete_prompt(None, "only")


if __name__ == "__main__":
    unittest.main()
