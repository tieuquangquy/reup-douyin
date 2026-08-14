from src.downloaders.post_download_qa import evaluate_post_download_qa
from src.render_pipeline.types import VideoProbe


def test_post_download_qa_warns_when_expected_audio_is_missing() -> None:
    qa = evaluate_post_download_qa(
        VideoProbe(
            width=1080,
            height=1920,
            fps=30.0,
            duration_seconds=10.0,
            video_codec="h264",
            audio_codec=None,
        ),
        advertised_width=1080,
        advertised_height=1920,
        expected_duration_seconds=12.0,
        expect_audio=True,
    )

    assert qa["status"] == "WARN"
    assert "expected_audio_stream_missing" in qa["warnings"]
    assert "measured_duration_differs_from_expected" in qa["warnings"]

