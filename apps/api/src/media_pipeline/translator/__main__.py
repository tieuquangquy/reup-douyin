"""
Phase 2.5 smoke test — uses Ops Caption AI settings (workspace DB).

Config UI:
  Ops Console → Caption AI settings
    - Caption AI: provider / base URL / key / model
    - Caption prompt: system prompt

Does NOT read or write Translation settings (dialogue).
"""

from __future__ import annotations

import json
import sys

from src.db.session import get_session_factory
from src.media_pipeline.translator.resolve import resolve_translator_settings
from src.media_pipeline.translator.service import translate_subtitles


def main() -> int:
    mock_ocr = {
        0: "今天天气真好，我们出去玩吧",
        1000: "这个短视频真的太有意思了",
        2000: "点赞关注，我们下期再见",
    }
    print("=== Phase 2.5 Caption AI smoke ===")
    print("input:", json.dumps(mock_ocr, ensure_ascii=False, indent=2))

    try:
        factory = get_session_factory()
        with factory() as db:
            settings = resolve_translator_settings(db=db, workspace_id=None)
            print(
                f"settings: source={settings.source} model={settings.model_name} "
                f"base_url={settings.base_url} timeout={settings.timeout_seconds}s"
            )
            print(f"prompt_preview: {settings.system_prompt[:120]}...")
            result = translate_subtitles(mock_ocr, db=db, settings=settings)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}", file=sys.stderr)
        print(
            "Fix: Ops Console → Caption AI settings → enable override, Save "
            "(+ Caption prompt). Translation settings are separate and untouched.",
            file=sys.stderr,
        )
        return 1

    print("output:", json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
