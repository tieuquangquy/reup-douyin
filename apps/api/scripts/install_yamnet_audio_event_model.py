"""Install the pinned local YAMNet model; runtime never downloads models."""

from __future__ import annotations

import hashlib
from pathlib import Path

import requests

from src.audio_pipeline.yamnet_audio_events import (
    YAMNET_CLASS_MAP_SHA256,
    YAMNET_MODEL_SHA256,
)
from src.core.settings import get_settings


REVISION = "f25b741c2f0bdc6d7e6db24b5fddda23347dbafd"
BASE = f"https://huggingface.co/audiomagic/yamnet-onnx/resolve/{REVISION}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path, expected: str) -> None:
    if destination.is_file() and _sha256(destination) == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with requests.get(url, stream=True, timeout=(15, 180)) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
    if _sha256(temporary) != expected:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 mismatch for {destination.name}")
    temporary.replace(destination)


def main() -> int:
    root = Path(str(get_settings().local_storage_root))
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    destination = root / ".models" / "audio_event" / "yamnet_f25b741c"
    _download(f"{BASE}/yamnet.onnx?download=true", destination / "yamnet.onnx", YAMNET_MODEL_SHA256)
    _download(
        f"{BASE}/yamnet_class_map.csv?download=true",
        destination / "yamnet_class_map.csv",
        YAMNET_CLASS_MAP_SHA256,
    )
    print(f"YAMNet local model ready: {destination}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
