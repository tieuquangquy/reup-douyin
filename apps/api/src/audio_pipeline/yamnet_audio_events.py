"""Pinned local YAMNet ONNX inference for AudioSet event evidence."""

from __future__ import annotations

import csv
import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from src.core.settings import get_settings


YAMNET_MODEL_VERSION = "yamnet-onnx-f25b741c-audioset521"
YAMNET_MODEL_SHA256 = "d3835ffbbd4a1bb3e777f0ca217b5007907f5171dd5d17c4236b95b2af8f908e"
YAMNET_CLASS_MAP_SHA256 = "cdf24d193e196d9e95912a2667051ae203e92a2ba09449218ccb40ef787c6df2"


@dataclass(frozen=True)
class YamnetFrameScores:
    speech: float
    singing: float
    music: float
    reaction: float
    silence_noise: float
    top_label: str
    top_score: float


@dataclass(frozen=True)
class YamnetEvidence:
    model_version: str
    model_sha256: str
    frames: tuple[YamnetFrameScores, ...]


def score_yamnet_waveform(waveform_16khz: np.ndarray) -> YamnetEvidence | None:
    """Return local AudioSet evidence, or None for a missing/invalid model."""

    enabled = bool(getattr(get_settings(), "audio_event_yamnet_enabled", True))
    if not enabled:
        return None
    model_path, class_map_path = _model_paths()
    if not _verified(model_path, YAMNET_MODEL_SHA256) or not _verified(
        class_map_path, YAMNET_CLASS_MAP_SHA256
    ):
        return None
    try:
        session, labels, groups = _runtime(str(model_path), str(class_map_path))
        scores = session.run(
            ["output_0"],
            {"waveform": np.asarray(waveform_16khz, dtype=np.float32)},
        )[0]
    except Exception:
        return None
    rows: list[YamnetFrameScores] = []
    for raw in np.asarray(scores):
        top_index = int(np.argmax(raw))
        rows.append(
            YamnetFrameScores(
                speech=_group_score(raw, groups["speech"]),
                singing=_group_score(raw, groups["singing"]),
                music=_group_score(raw, groups["music"]),
                reaction=_group_score(raw, groups["reaction"]),
                silence_noise=_group_score(raw, groups["silence_noise"]),
                top_label=labels[top_index],
                top_score=round(float(raw[top_index]), 6),
            )
        )
    return YamnetEvidence(
        model_version=YAMNET_MODEL_VERSION,
        model_sha256=YAMNET_MODEL_SHA256,
        frames=tuple(rows),
    )


def _model_paths() -> tuple[Path, Path]:
    configured = str(
        getattr(get_settings(), "audio_event_yamnet_model_path", "") or ""
    ).strip()
    if configured:
        model = Path(configured)
        if not model.is_absolute():
            model = (Path.cwd() / model).resolve()
        return model, model.with_name("yamnet_class_map.csv")
    storage_root = Path(str(get_settings().local_storage_root))
    if not storage_root.is_absolute():
        storage_root = (Path.cwd() / storage_root).resolve()
    root = storage_root / ".models" / "audio_event" / "yamnet_f25b741c"
    return root / "yamnet.onnx", root / "yamnet_class_map.csv"


@lru_cache(maxsize=2)
def _runtime(model_path: str, class_map_path: str):
    import onnxruntime as ort

    labels = _labels(Path(class_map_path))
    groups = _groups(labels)
    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, min(4, int(os.cpu_count() or 1)))
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        model_path,
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    return session, labels, groups


def _labels(path: Path) -> tuple[str, ...]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    labels = tuple(str(row.get("display_name") or "") for row in rows)
    if len(labels) != 521:
        raise ValueError("yamnet_class_map_must_have_521_rows")
    return labels


def _groups(labels: tuple[str, ...]) -> dict[str, tuple[int, ...]]:
    def indices(predicate) -> tuple[int, ...]:
        return tuple(index for index, label in enumerate(labels) if predicate(label.casefold()))

    singing_terms = (
        "singing",
        "choir",
        "chant",
        "rapping",
        "humming",
        "yodeling",
        "vocal music",
    )
    reaction_terms = (
        "laughter",
        "crying",
        "sobbing",
        "cough",
        "sneeze",
        "gasp",
        "breathing",
        "screaming",
        "shout",
        "yell",
        "applause",
        "cheering",
    )
    noise_terms = ("silence", "noise", "static", "sound effect")
    return {
        "speech": indices(
            lambda value: value
            in {
                "speech",
                "conversation",
                "narration, monologue",
                "male speech, man speaking",
                "female speech, woman speaking",
                "child speech, kid speaking",
                "whispering",
                "speech synthesizer",
            }
        ),
        "singing": indices(lambda value: any(term in value for term in singing_terms)),
        "music": indices(
            lambda value: value == "music"
            or " music" in value
            or value.endswith("music")
            or value == "musical instrument"
        ),
        "reaction": indices(lambda value: any(term in value for term in reaction_terms)),
        "silence_noise": indices(lambda value: any(term in value for term in noise_terms)),
    }


def _group_score(scores: np.ndarray, indices: tuple[int, ...]) -> float:
    if not indices:
        return 0.0
    values = np.asarray(scores)[list(indices)]
    # AudioSet is multi-label. Max preserves a strong child/parent class while
    # the small second-best contribution makes related evidence less brittle.
    ordered = np.sort(values)
    score = float(ordered[-1])
    if ordered.size > 1:
        score = min(1.0, score + 0.20 * float(ordered[-2]))
    return round(score, 6)


@lru_cache(maxsize=8)
def _verified(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().casefold() == expected.casefold()
