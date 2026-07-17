"""Convert full Google Sans TTFs to WOFF2 (no glyph subset).

Run from apps/web (or any cwd):

  python scripts/convert_google_sans_woff2.py

Requires: pip install fonttools brotli

Reads full TTFs from fonts/google-sans-src/ and writes WOFF2
files to public/fonts/google-sans/ for runtime.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont

WEB_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WEB_ROOT / "fonts" / "google-sans-src"
OUT_DIR = WEB_ROOT / "public" / "fonts" / "google-sans"

SOURCES = (
    "GoogleSans-Regular.ttf",
    "GoogleSans-Medium.ttf",
    "GoogleSans-Bold.ttf",
)


def convert_to_woff2(src: Path, dest: Path) -> None:
    font = TTFont(src)
    font.flavor = "woff2"
    dest.parent.mkdir(parents=True, exist_ok=True)
    font.save(dest)
    font.close()


def main() -> None:
    if not SRC_DIR.is_dir():
        raise SystemExit(
            f"Font source directory not found: {SRC_DIR}\n"
            "Place full GoogleSans-*.ttf files there before running."
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        src = SRC_DIR / name
        if not src.is_file():
            print(f"skip missing {src}")
            continue
        dest = OUT_DIR / (src.stem + ".woff2")
        convert_to_woff2(src, dest)
        ttf_kb = src.stat().st_size / 1024
        woff_kb = dest.stat().st_size / 1024
        print(f"{dest.name}: {woff_kb:.1f} KB (full face from {ttf_kb:.1f} KB TTF)")


if __name__ == "__main__":
    main()
