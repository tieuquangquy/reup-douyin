"""Finalize an operator-approved NO_TEXT case without OCR/TTS invention."""

from __future__ import annotations

import argparse
import json
import sys

from src.services.no_text_passthrough import (
    NoTextPassthroughError,
    finalize_no_text_passthrough,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.finalize_no_text_passthrough"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("--operator", required=True)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        result = finalize_no_text_passthrough(
            root_dir=args.artifact_root, operator_id=args.operator
        )
    except (OSError, ValueError, NoTextPassthroughError) as exc:
        print(f"[NO-TEXT-PASSTHROUGH][FAIL] {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

