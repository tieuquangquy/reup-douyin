from src.audio_pipeline.quality_metrics import evaluate_audio_quality


def test_exact_transcript_and_timeline_score_perfectly() -> None:
    result = evaluate_audio_quality(
        reference_text="hello world",
        predicted_text="hello world",
        reference_intervals=[[0.0, 1.0], [2.0, 3.0]],
        predicted_intervals=[[0.0, 1.0], [2.0, 3.0]],
    )
    assert result.cer == 0.0
    assert result.wer == 0.0
    assert result.timing_iou == 1.0
    assert result.false_dialogue_rate == 0.0
    assert result.missed_dialogue_rate == 0.0


def test_false_and_missed_dialogue_are_reported_separately() -> None:
    result = evaluate_audio_quality(
        reference_text="one two",
        predicted_text="one too",
        reference_intervals=[[0.0, 1.0], [4.0, 5.0]],
        predicted_intervals=[[0.0, 1.0], [8.0, 9.0]],
    )
    assert result.cer > 0.0
    assert result.wer == 0.5
    assert result.timing_iou == 0.5
    assert result.false_dialogue_rate == 0.5
    assert result.missed_dialogue_rate == 0.5


def test_empty_reference_does_not_divide_by_zero() -> None:
    result = evaluate_audio_quality(
        reference_text="",
        predicted_text="hallucination",
        reference_intervals=[],
        predicted_intervals=[[1.0, 2.0]],
    )
    assert result.cer == 1.0
    assert result.wer == 1.0
    assert result.false_dialogue_rate == 1.0
    assert result.missed_dialogue_rate == 0.0
