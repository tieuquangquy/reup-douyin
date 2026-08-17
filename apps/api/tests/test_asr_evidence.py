from __future__ import annotations

from dataclasses import dataclass, field

from src.audio_pipeline.asr_evidence import (
    ASREvidenceState,
    compare_asr_stability,
    evaluate_asr_evidence,
    evidence_prefers_candidate,
)


@dataclass
class Unit:
    text: str
    start_seconds: float
    end_seconds: float
    confidence: float | None = None
    flags: list[str] = field(default_factory=list)


def test_good_dialogue_scores_high_without_recovery() -> None:
    evidence = evaluate_asr_evidence(
        [
            Unit("今天我们去北京", 0.0, 1.8, 0.91),
            Unit("然后一起吃饭", 1.95, 3.7, 0.89),
            Unit("下午再回来", 3.85, 5.3, 0.93),
        ]
    )

    assert evidence.state == ASREvidenceState.GOOD
    assert evidence.overall_score >= 0.80
    assert evidence.recovery_recommended is False
    assert evidence.timed_unit_ratio == 1.0
    assert evidence.confidence_coverage == 1.0


def test_high_confidence_repetition_and_impossible_rate_is_not_trusted() -> None:
    evidence = evaluate_asr_evidence(
        [
            Unit("哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈", 0.0, 0.22, 0.98),
            Unit("哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈", 0.23, 0.46, 0.97),
            Unit("哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈", 0.47, 0.70, 0.96),
        ]
    )

    assert evidence.state in {ASREvidenceState.WEAK, ASREvidenceState.BORDERLINE}
    assert evidence.overall_score < 0.72
    assert evidence.recovery_recommended is True
    assert "high_text_repetition" in evidence.reasons
    assert "implausible_text_rate" in evidence.reasons


def test_untimed_flags_lower_temporal_evidence() -> None:
    clean = evaluate_asr_evidence(
        [
            Unit("这个产品今天介绍一下", 0.0, 2.0, 0.86),
            Unit("先看它的主要特点", 2.1, 4.2, 0.88),
        ]
    )
    untimed = evaluate_asr_evidence(
        [
            Unit("这个产品今天介绍一下", 0.0, 0.0, 0.86, ["funasr_untimed"]),
            Unit("先看它的主要特点", 0.0, 0.0, 0.88, ["funasr_untimed"]),
        ]
    )

    assert untimed.temporal_score < clean.temporal_score
    assert untimed.overall_score < clean.overall_score
    assert "funasr_untimed_present" in untimed.reasons


def test_empty_asr_is_explicit_recovery_state() -> None:
    evidence = evaluate_asr_evidence([])

    assert evidence.state == ASREvidenceState.EMPTY
    assert evidence.overall_score == 0.0
    assert evidence.recovery_recommended is True
    assert evidence.reasons == ("no_asr_units",)


def test_stability_score_penalizes_borderline_disagreement() -> None:
    primary = [Unit("今天我们去北京然后吃饭", 0.0, 3.0, 0.87)]
    similar = [Unit("今天我们去北京，然后吃饭。", 0.0, 3.0, 0.85)]
    different = [Unit("欢迎关注点赞支持主播", 0.0, 3.0, 0.85)]

    stable_score = compare_asr_stability(primary, similar)
    unstable_score = compare_asr_stability(primary, different)

    assert stable_score is not None and stable_score > 0.9
    assert unstable_score is not None and unstable_score < 0.5
    stable = evaluate_asr_evidence(primary, stability_score=stable_score)
    unstable = evaluate_asr_evidence(primary, stability_score=unstable_score)
    assert stable.overall_score > unstable.overall_score


def test_arbitration_prefers_better_evidence_and_supports_future_min_gain() -> None:
    mixed = evaluate_asr_evidence(
        [Unit("今天介绍这个产品", 0.0, 2.2, 0.69)]
    )
    separated = evaluate_asr_evidence(
        [Unit("今天给大家介绍这个产品", 0.0, 2.2, 0.91)]
    )

    assert evidence_prefers_candidate(separated, mixed)
    assert not evidence_prefers_candidate(mixed, separated)
    assert not evidence_prefers_candidate(separated, mixed, min_gain=0.5)


def test_stability_aligns_primary_to_selective_verification_spans() -> None:
    primary = [
        Unit("前面这句没有复核", 0.0, 2.0, 0.9),
        Unit("需要复核的这一句", 5.0, 7.0, 0.8),
        Unit("后面这句也没有复核", 9.0, 11.0, 0.9),
    ]
    verification = [Unit("需要复核的这一句", 5.1, 6.9, 0.82)]

    score = compare_asr_stability(primary, verification)

    assert score is not None and score > 0.95


def test_invalid_replacement_char_is_visible_in_evidence_reasons() -> None:
    evidence = evaluate_asr_evidence(
        [Unit("正常文本�\x00�异常", 0.0, 1.5, 0.82)]
    )

    assert evidence.invalid_char_ratio > 0.08
    assert "invalid_text_content" in evidence.reasons
