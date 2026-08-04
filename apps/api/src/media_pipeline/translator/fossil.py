"""Write Phase 2.5 translate QA fossils for audit / re-render without LLM."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)


def write_translate_fossils(
    artifact_dir: str | Path,
    *,
    unique_zh_to_vi: Mapping[str, str],
    vi_texts: Mapping[str, str],
    stats: Mapping[str, Any],
) -> dict[str, str]:
    """
    Persist ``translate_unique.json``, ``vi_texts.json``, ``translate_stats.json``.

    Returns paths written (posix strings).
    """
    root = Path(artifact_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "translate_unique": root / "translate_unique.json",
        "vi_texts": root / "vi_texts.json",
        "translate_stats": root / "translate_stats.json",
    }
    paths["translate_unique"].write_text(
        json.dumps(dict(unique_zh_to_vi), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["vi_texts"].write_text(
        json.dumps(dict(vi_texts), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["translate_stats"].write_text(
        json.dumps(dict(stats), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "caption_translate_fossils unique=%s vi_keys=%s dir=%s",
        len(unique_zh_to_vi),
        len(vi_texts),
        root.as_posix(),
    )
    return {name: path.as_posix() for name, path in paths.items()}
