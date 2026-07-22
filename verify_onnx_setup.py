#!/usr/bin/env python3
"""QA smoke checks for LocalTextDetector (ONNX DBNet) Phase 1 keyframes.

Run from repo root:
    python verify_onnx_setup.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent
API_ROOT = REPO_ROOT / "apps" / "api"
MODEL_PATH = API_ROOT / "models" / "dbnet.onnx"
PYPROJECT = API_ROOT / "pyproject.toml"
FRAME_SAMPLING_REQUIREMENTS = (
    API_ROOT / "src" / "media_pipeline" / "frame_sampling" / "requirements.txt"
)

# chineseocr_lite onnx branch — same default as ensure_dbnet_model.py
DEFAULT_DBNET_URL = (
    "https://github.com/DayBreak-u/chineseocr_lite/raw/onnx/models/dbnet.onnx"
)
_MIN_MODEL_BYTES = 100_000

# Ensure API package imports work when run from repo root
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# ---------------------------------------------------------------------------
# ANSI colors (no extra deps)
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def green(text: str) -> str:
    return _c("32;1", text)


def red(text: str) -> str:
    return _c("31;1", text)


def cyan(text: str) -> str:
    return _c("36;1", text)


def yellow(text: str) -> str:
    return _c("33;1", text)


def dim(text: str) -> str:
    return _c("2", text)


def banner(title: str) -> None:
    line = "═" * 56
    print()
    print(cyan(f"╔{line}╗"))
    print(cyan(f"║  {title:<52}  ║"))
    print(cyan(f"╚{line}╝"))


def pass_line(name: str, detail: str = "") -> None:
    extra = f"  {dim(detail)}" if detail else ""
    print(f"  {green('[PASS]')}  {name}{extra}")


def fail_line(name: str, detail: str = "") -> None:
    extra = f"  {dim(detail)}" if detail else ""
    print(f"  {red('[FAIL]')}  {name}{extra}")


def info_line(msg: str) -> None:
    print(f"  {yellow('[INFO]')}  {msg}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def test_dependencies() -> bool:
    """Declare onnxruntime + opencv in API deps (pyproject; Alpine reqs stay empty)."""
    banner("1 / 3  Test Dependencies")
    ok = True

    pyproject = _read_text(PYPROJECT)
    alpine_req = _read_text(FRAME_SAMPLING_REQUIREMENTS)

    # Primary authority for worker/API: pyproject.toml
    has_ort = "onnxruntime" in pyproject
    has_cv2 = "opencv-python" in pyproject  # matches opencv-python-headless too

    if not PYPROJECT.is_file():
        fail_line("apps/api/pyproject.toml", "file missing")
        ok = False
    else:
        info_line(f"Checked {PYPROJECT.relative_to(REPO_ROOT)}")
        if has_ort:
            pass_line("onnxruntime declared in pyproject.toml")
        else:
            fail_line("onnxruntime declared in pyproject.toml", "not found")
            ok = False
        if has_cv2:
            pass_line("opencv-python* declared in pyproject.toml")
        else:
            fail_line("opencv-python* declared in pyproject.toml", "not found")
            ok = False

    # Alpine Cloud Run requirements intentionally omit onnx (plan non-goal)
    info_line(
        f"Checked {FRAME_SAMPLING_REQUIREMENTS.relative_to(REPO_ROOT)} "
        "(Alpine image — onnxruntime must NOT be required here)"
    )
    if "onnxruntime" in alpine_req:
        fail_line(
            "frame_sampling/requirements.txt stays onnx-free",
            "onnxruntime listed — Cloud Run Alpine would break",
        )
        ok = False
    else:
        pass_line("frame_sampling/requirements.txt has no onnxruntime (expected)")

    # Runtime packages actually importable
    for mod_name, label in (("onnxruntime", "onnxruntime"), ("cv2", "opencv (cv2)")):
        if importlib.util.find_spec(mod_name) is None:
            fail_line(f"import {label}", "not installed in this Python")
            ok = False
        else:
            pass_line(f"import {label}")

    return ok


def test_model_check_and_download() -> bool:
    """Ensure apps/api/models/dbnet.onnx exists; download if missing."""
    banner("2 / 3  Test Model Check & Download")
    models_dir = MODEL_PATH.parent

    if models_dir.is_dir():
        pass_line("models directory exists", str(models_dir.relative_to(REPO_ROOT)))
    else:
        info_line(f"Creating {models_dir.relative_to(REPO_ROOT)}")
        models_dir.mkdir(parents=True, exist_ok=True)
        pass_line("models directory created")

    existing = MODEL_PATH.is_file() and MODEL_PATH.stat().st_size >= _MIN_MODEL_BYTES
    if existing:
        size_kb = MODEL_PATH.stat().st_size / 1024
        pass_line("dbnet.onnx present", f"{size_kb:.1f} KB")
        return True

    info_line("dbnet.onnx missing or too small — downloading…")
    url = (os.environ.get("DBNET_ONNX_URL") or DEFAULT_DBNET_URL).strip()
    info_line(f"URL: {url}")

    try:
        # Prefer repo helper (same URL + size gate)
        from src.media_pipeline.frame_sampling.ensure_dbnet_model import (  # noqa: WPS433
            ensure_dbnet_onnx,
        )

        path = ensure_dbnet_onnx(MODEL_PATH)
        size_kb = path.stat().st_size / 1024
        pass_line("dbnet.onnx downloaded via ensure_dbnet_onnx", f"{size_kb:.1f} KB")
        return True
    except Exception as exc:  # noqa: BLE001
        # Fallback: raw urllib
        try:
            import urllib.request

            tmp = MODEL_PATH.with_suffix(".onnx.partial")
            urllib.request.urlretrieve(url, str(tmp))  # noqa: S310
            size = tmp.stat().st_size if tmp.is_file() else 0
            if size < _MIN_MODEL_BYTES:
                tmp.unlink(missing_ok=True)
                fail_line("download dbnet.onnx", f"too small ({size} bytes); helper err: {exc}")
                return False
            tmp.replace(MODEL_PATH)
            pass_line(
                "dbnet.onnx downloaded via urllib",
                f"{MODEL_PATH.stat().st_size / 1024:.1f} KB",
            )
            return True
        except Exception as exc2:  # noqa: BLE001
            fail_line("download dbnet.onnx", f"{exc2}")
            return False


def test_inference() -> bool:
    """Smoke-run LocalTextDetector on a random BGR dummy frame."""
    banner("3 / 3  Test Inference (LocalTextDetector)")

    try:
        import numpy as np

        from src.media_pipeline.frame_sampling.local_text_detector import LocalTextDetector
    except Exception as exc:  # noqa: BLE001
        fail_line("import LocalTextDetector", str(exc))
        traceback.print_exc()
        return False

    pass_line("import LocalTextDetector")

    if not MODEL_PATH.is_file():
        fail_line("model path for inference", f"missing {MODEL_PATH}")
        return False

    try:
        detector = LocalTextDetector(MODEL_PATH)
        pass_line("LocalTextDetector initialized", str(MODEL_PATH.name))
    except Exception as exc:  # noqa: BLE001
        fail_line("LocalTextDetector init", str(exc))
        traceback.print_exc()
        return False

    rng = np.random.default_rng(42)
    dummy = rng.integers(0, 256, size=(640, 640, 3), dtype=np.uint8)
    info_line(f"Dummy BGR image shape={dummy.shape} dtype={dummy.dtype}")

    try:
        boxes = detector.detect(dummy)
        # Random noise may yield 0 boxes — that is still a successful forward pass
        pass_line(
            "detect() forward pass",
            f"boxes={len(boxes)} (0 is OK on noise)",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        fail_line("detect() forward pass", str(exc))
        traceback.print_exc()
        return False


def main() -> int:
    print(cyan("\n  ◆  ONNX LocalTextDetector — QA Setup Verifier"))
    print(dim(f"  repo: {REPO_ROOT}"))
    print(dim(f"  python: {sys.executable} ({sys.version.split()[0]})"))

    results = [
        ("Dependencies", test_dependencies()),
        ("Model Check & Download", test_model_check_and_download()),
        ("Inference", test_inference()),
    ]

    banner("SUMMARY")
    all_ok = True
    for name, ok in results:
        if ok:
            pass_line(name)
        else:
            fail_line(name)
            all_ok = False

    print()
    if all_ok:
        print(green("  ★  ALL CHECKS PASSED — module ready for ANALYZE_OCR (text_onnx)"))
        print()
        return 0

    print(red("  ✖  ONE OR MORE CHECKS FAILED — see details above"))
    print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
