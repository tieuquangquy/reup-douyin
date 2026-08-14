from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.schemas.downloads import DownloadCreateRequest


def test_download_request_requires_exactly_one_source_selector() -> None:
    with pytest.raises(ValidationError, match="Exactly one"):
        DownloadCreateRequest()

    with pytest.raises(ValidationError, match="Exactly one"):
        DownloadCreateRequest(source_video_id=uuid4(), candidate_id=uuid4())


def test_download_request_accepts_source_or_candidate_selector() -> None:
    source_id = uuid4()
    candidate_id = uuid4()

    assert DownloadCreateRequest(source_video_id=source_id).source_video_id == source_id
    assert DownloadCreateRequest(candidate_id=candidate_id).candidate_id == candidate_id
