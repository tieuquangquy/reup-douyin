from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_AUTH_REQUIRED", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-at-least-thirty-two-characters")

from fastapi.testclient import TestClient

from src.api.routes.capture_inbox import get_capture_inbox_service
from src.core.settings import get_settings
from src.main import create_app
from src.services.capture_inbox_service import (
    CaptureInboxService,
    _thumbnail_fetch_candidates,
)

UNSIGNED_DOYIN_THUMB = (
    "https://p3-sign.douyinpic.com/aweme/100x100/cover~noop.jpeg?from=327834062"
)
SIGNED_DOYIN_THUMB = (
    "https://p3-sign.douyinpic.com/aweme/720x720/cover.jpeg"
    "?x-signature=signed-example&x-expires=4102444800"
)


def _thumbnail_item(**overrides):
    payload = {
        "thumbnail_url": UNSIGNED_DOYIN_THUMB,
        "preview_url": None,
        "raw_payload_json": {
            "profile_card_evidence": {
                "cover": {
                    "url_list": [SIGNED_DOYIN_THUMB],
                }
            }
        },
        "metadata_json": {},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class CaptureInboxThumbnailProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        self.app = create_app()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        get_settings.cache_clear()

    def test_thumbnail_fetch_candidates_prefers_signed_url_over_unsigned_column(self) -> None:
        candidates = _thumbnail_fetch_candidates(_thumbnail_item())

        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(candidates[0], SIGNED_DOYIN_THUMB)
        self.assertIn(UNSIGNED_DOYIN_THUMB, candidates)

    @patch("src.services.capture_inbox_service.urlopen")
    def test_stream_item_thumbnail_uses_signed_candidate_first(self, mock_urlopen: MagicMock) -> None:
        item = _thumbnail_item()
        service = CaptureInboxService(db=MagicMock())
        service.get_item = MagicMock(return_value=item)  # type: ignore[method-assign]

        response = MagicMock()
        response.headers.get_content_type.return_value = "image/jpeg"
        response.read.return_value = b"\xff\xd8\xff\xd9"
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        mock_urlopen.return_value = response

        data, content_type = service.stream_item_thumbnail(uuid4())

        self.assertEqual(data, b"\xff\xd8\xff\xd9")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(mock_urlopen.call_count, 1)
        first_url = mock_urlopen.call_args.args[0].full_url
        self.assertIn("x-signature=", first_url.lower())

    @patch("src.services.capture_inbox_service.urlopen")
    def test_stream_item_thumbnail_falls_back_when_signed_returns_403(self, mock_urlopen: MagicMock) -> None:
        item = _thumbnail_item()
        service = CaptureInboxService(db=MagicMock())
        service.get_item = MagicMock(return_value=item)  # type: ignore[method-assign]

        def _urlopen_side_effect(request, timeout=12):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if "x-signature=" in url.lower():
                raise HTTPError(url, 403, "Forbidden", hdrs=None, fp=None)
            response = MagicMock()
            response.headers.get_content_type.return_value = "image/jpeg"
            response.read.return_value = b"\xff\xd8\xff\xd9"
            response.__enter__.return_value = response
            response.__exit__.return_value = False
            return response

        mock_urlopen.side_effect = _urlopen_side_effect

        data, content_type = service.stream_item_thumbnail(uuid4())

        self.assertEqual(data, b"\xff\xd8\xff\xd9")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(mock_urlopen.call_count, 2)
        signed_url = mock_urlopen.call_args_list[0].args[0].full_url
        unsigned_url = mock_urlopen.call_args_list[1].args[0].full_url
        self.assertIn("x-signature=", signed_url.lower())
        self.assertNotIn("x-signature=", unsigned_url.lower())

    def test_thumbnail_route_is_accessible_without_bearer_for_img_tags(self) -> None:
        mock_service = MagicMock()
        mock_service.stream_item_thumbnail.return_value = (b"\xff\xd8\xff\xd9", "image/jpeg")
        self.app.dependency_overrides[get_capture_inbox_service] = lambda: mock_service
        item_id = uuid4()

        with TestClient(self.app) as client:
            response = client.get(f"/capture-inbox/items/{item_id}/thumbnail")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("image/"))
        self.assertEqual(response.content, b"\xff\xd8\xff\xd9")
        mock_service.stream_item_thumbnail.assert_called_once_with(item_id)


if __name__ == "__main__":
    unittest.main()
