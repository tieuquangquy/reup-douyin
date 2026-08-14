from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from src.services.quality_auto_policy import translate_residual_texts
from src.services.residual_translation import normalize_residual_detections


def test_temporal_normalization_collapses_frame_rows_and_protects_source() -> None:
    caption_geometry = {"x": 0.2, "y": 0.78, "width": 0.6, "height": 0.04}
    phone_geometry = {"x": 0.55, "y": 0.10, "width": 0.20, "height": 0.08}
    detections = [
        {
            "frame_index": frame,
            "text": "字幕测试" if frame != 12 else "字幕测式",
            "confidence": 0.96 if frame != 12 else 0.72,
            "geometry": caption_geometry,
        }
        for frame in range(10, 21)
    ] + [
        {
            "frame_index": frame,
            "text": "手机设置",
            "confidence": 0.98,
            "geometry": phone_geometry,
        }
        for frame in range(30, 36)
    ]
    protected_tracks = [
        {
            "text_id": "phone_ui",
            "start_frame": 28,
            "end_frame": 40,
            "box_coords": [550, 100, 750, 180],
            "visual_provenance": {"classification": "SOURCE_INTRINSIC_PANEL"},
            "action": "PRESERVE_SOURCE_PIXELS",
        }
    ]

    rows, audit = normalize_residual_detections(
        detections,
        protected_tracks=protected_tracks,
        frame_width=1000,
        frame_height=1000,
    )

    assert len(rows) == 1
    assert rows[0]["text"] == "字幕测试"
    assert rows[0]["start_frame"] == 10
    assert rows[0]["end_frame"] == 20
    assert rows[0]["detection_count"] == 11
    assert audit["raw_detection_count"] == 17
    assert audit["temporal_content_count"] == 2
    assert audit["protected_source_content_count"] == 1


def test_temporal_normalization_drops_unconfirmed_low_confidence_single_glyph() -> None:
    rows, audit = normalize_residual_detections(
        [
            {
                "frame_index": 2254,
                "text": "發味",
                "confidence": 0.2811,
                "geometry": {
                    "x": 0.70,
                    "y": 0.45,
                    "width": 0.09,
                    "height": 0.025,
                },
                "temporal_confirmation": {
                    "status": "SINGLE_FRAME_CJK_FAIL_CLOSED",
                    "checked_frames": [2253, 2255],
                },
            }
        ],
        frame_width=1080,
        frame_height=1920,
    )

    assert rows == []
    assert audit["raw_detection_count"] == 1
    assert audit["review_content_count"] == 0


def test_translation_batches_and_resumes_from_content_cache(tmp_path) -> None:
    calls: list[list[str]] = []

    def complete(**kwargs):
        request = json.loads(kwargs["messages"][1]["content"])
        calls.append(list(request))
        payload = {
            key: {
                "zh_corrected": row["ocr_text"],
                "vi_text": f"VI {row['ocr_text']}",
            }
            for key, row in request.items()
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=complete))
    )
    settings = SimpleNamespace(
        model_name="model",
        api_key="key",
        base_url="url",
        system_prompt="prompt",
    )
    objects = [
        {"content_id": f"content_{index}", "text": f"中文{index}"}
        for index in range(7)
    ]
    cache_path = tmp_path / "residual_cache.json"
    with patch(
        "src.media_pipeline.translator.resolve.resolve_translator_settings",
        return_value=settings,
    ), patch(
        "src.media_pipeline.translator.client.build_openai_client",
        return_value=client,
    ):
        first = translate_residual_texts(
            db=object(),
            workspace_id=object(),
            residual_objects=objects,
            cache_path=cache_path,
            batch_size=3,
        )
        first_call_count = len(calls)
        second = translate_residual_texts(
            db=object(),
            workspace_id=object(),
            residual_objects=objects,
            cache_path=cache_path,
            batch_size=3,
        )

    assert len(first) == len(second) == 7
    assert [len(batch) for batch in calls] == [3, 3, 1]
    assert len(calls) == first_call_count


def test_translation_bisects_failed_large_batch(tmp_path) -> None:
    calls: list[int] = []

    def complete(**kwargs):
        request = json.loads(kwargs["messages"][1]["content"])
        calls.append(len(request))
        if len(request) > 3:
            raise RuntimeError("HTTP 500")
        payload = {
            key: {"zh_corrected": row["ocr_text"], "vi_text": "Bản dịch"}
            for key, row in request.items()
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=complete))
    )
    settings = SimpleNamespace(
        model_name="model",
        api_key="key",
        base_url="url",
        system_prompt="prompt",
    )
    with patch(
        "src.media_pipeline.translator.resolve.resolve_translator_settings",
        return_value=settings,
    ), patch(
        "src.media_pipeline.translator.client.build_openai_client",
        return_value=client,
    ):
        rows = translate_residual_texts(
            db=object(),
            workspace_id=object(),
            residual_objects=[{"text": f"中文{index}"} for index in range(6)],
            cache_path=tmp_path / "cache.json",
            batch_size=12,
        )

    assert len(rows) == 6
    assert calls == [6, 3, 3]
