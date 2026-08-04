"""Step 2: Cloud OCR on keyframe crops — local sharpen, async /predict, hallucination filter."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import aiohttp
import cv2
import numpy as np
from tqdm.asyncio import tqdm as tqdm_asyncio

from src.media_pipeline.ocr_filtering.providers import (
    normalize_predict_endpoint,
    resolve_ocr_endpoint_url,
    resolve_ocr_http_timeout_seconds,
)

logger = logging.getLogger(__name__)

SHARPEN_KERNEL = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
NOISE_SINGLE_CHARS = frozenset({"一", "丨", "丶", "-", ".", ",", "!", "l", "I"})
_SPECIAL_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)
_DEFAULT_CONCURRENCY = 4  # Prompt 2 default: asyncio.Semaphore(4)
OCR_ASYNC_CONCURRENCY_ENV = "OCR_ASYNC_CONCURRENCY"
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_RETRY_DELAY_S = 1.0
_JPEG_QUALITY = 95
_MIN_SCORE = 0.7
_MIN_BOX_HEIGHT_PX = 10.0
_RECOG_PAD_FRAC = 0.12
_RECOG_MIN_HEIGHT_PX = 48
_GARBAGE_QMARK_RATIO = 0.25
_GARBAGE_MEANINGFUL_RATIO = 0.45


def resolve_analyze_concurrency(default: int = _DEFAULT_CONCURRENCY) -> int:
    """Default 4 (Prompt 2); override via ``OCR_ASYNC_CONCURRENCY`` for local stability."""
    raw = (os.environ.get(OCR_ASYNC_CONCURRENCY_ENV) or "").strip()
    if not raw:
        return max(1, int(default))
    try:
        return max(1, int(raw))
    except ValueError:
        return max(1, int(default))


CropItem = dict[str, Any]
CleanHit = dict[str, Any]
GroupedResult = dict[str, list[CleanHit]]


class RetryableHttpError(Exception):
    """HTTP 50x — eligible for retry (Prompt 2: Timeout hoặc HTTP 50x)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)


def format_timestamp_key(seconds: float) -> str:
    """Format seconds → ``MM:SS.mmm`` (e.g. 5.5 → ``00:05.500``)."""
    total_ms = int(round(float(seconds) * 1000.0))
    if total_ms < 0:
        total_ms = 0
    mins, rem_ms = divmod(total_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{mins:02d}:{secs:02d}.{ms:03d}"


def original_box_to_quad(coords: list[float] | tuple[float, ...] | np.ndarray) -> list[float]:
    """
    Normalize ``original_box_coords`` to an 8-value quad without mutating geometry.

    Accepts xyxy ``[x1,y1,x2,y2]`` or already-flat quad ``[x1,y1,...,x4,y4]``.
    """
    vals = [float(v) for v in list(coords)]
    if len(vals) == 4:
        x0, y0, x1, y1 = vals
        return [x0, y0, x1, y0, x1, y1, x0, y1]
    if len(vals) >= 8:
        return vals[:8]
    raise ValueError(f"original_box_coords must be xyxy or 8-point quad, got len={len(vals)}")


def box_height_px(box_coords: list[float]) -> float:
    ys = box_coords[1::2]
    if not ys:
        return 0.0
    return float(max(ys) - min(ys))


def prepare_recognition_crop(
    frame_bgr: np.ndarray,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    pad_frac: float = _RECOG_PAD_FRAC,
    min_height_px: int = _RECOG_MIN_HEIGHT_PX,
) -> np.ndarray:
    """
    Color crop for long-line OCR: pad box → CLAHE on L → optional upscale.

    Keeps BGR (orange hardsubs / UI) unlike BW Otsu debug crops.
    Does **not** mutate the caller's stored ``original_box_coords``.
    """
    if frame_bgr is None or frame_bgr.size == 0:
        raise ValueError("frame_bgr is empty")
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    bw = max(1.0, float(x1) - float(x0))
    bh = max(1.0, float(y1) - float(y0))
    pad_x = bw * float(pad_frac)
    pad_y = bh * max(float(pad_frac), 0.18)  # extra vertical for clipped glyphs
    ix0 = max(0, min(w - 1, int(round(float(x0) - pad_x))))
    iy0 = max(0, min(h - 1, int(round(float(y0) - pad_y))))
    ix1 = max(ix0 + 1, min(w, int(round(float(x1) + pad_x))))
    iy1 = max(iy0 + 1, min(h, int(round(float(y1) + pad_y))))
    crop = frame_bgr[iy0:iy1, ix0:ix1].copy()
    if crop.ndim == 2:
        crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_ch = clahe.apply(l_ch)
    crop = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
    ch, cw = int(crop.shape[0]), int(crop.shape[1])
    if ch > 0 and ch < int(min_height_px):
        scale = float(min_height_px) / float(ch)
        crop = cv2.resize(
            crop,
            (max(1, int(round(cw * scale))), int(min_height_px)),
            interpolation=cv2.INTER_CUBIC,
        )
    return crop


def preprocess_crop_to_jpeg_b64(image_crop: np.ndarray) -> tuple[str, bytes]:
    """
    Mild sharpen on color (or gray→BGR) → JPEG q=95 → (base64, raw jpeg bytes).

    Color is required for long Douyin hardsubs / UI labels; do not force BW.
    Does **not** change any bounding-box coordinates (crop-only image ops).
    """
    if image_crop is None or getattr(image_crop, "size", 0) == 0:
        raise ValueError("image_crop is empty")
    arr = np.asarray(image_crop)
    if arr.ndim == 2:
        bgr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    elif arr.ndim == 3 and arr.shape[2] >= 3:
        bgr = arr[:, :, :3].copy()
    else:
        raise ValueError(f"Unsupported image_crop shape: {getattr(arr, 'shape', None)}")
    sharpened = cv2.filter2D(bgr, -1, SHARPEN_KERNEL)
    ok, buf = cv2.imencode(
        ".jpg",
        sharpened,
        [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY],
    )
    if not ok:
        raise RuntimeError("Failed to encode recognition crop as JPEG")
    jpeg = bytes(buf)
    return base64.b64encode(jpeg).decode("ascii"), jpeg


def _meaningful_char_count(text: str) -> int:
    n = 0
    for ch in text:
        if ch.isalnum():
            n += 1
        elif "\u4e00" <= ch <= "\u9fff":
            n += 1
    return n


def is_garbage_ocr_text(text: str) -> bool:
    """True when OCR output is mostly ``?`` / undecodable junk (long-line failure mode)."""
    raw = str(text or "").strip()
    if not raw:
        return True
    qmarks = sum(1 for ch in raw if ch in "?\ufffd")
    if qmarks / max(1, len(raw)) >= _GARBAGE_QMARK_RATIO:
        return True
    meaningful = _meaningful_char_count(raw)
    if meaningful == 0:
        return True
    if len(raw) >= 3 and meaningful / len(raw) < _GARBAGE_MEANINGFUL_RATIO:
        return True
    return False


def clean_ocr_data(
    text: str,
    score: float,
    box_coords: list[float],
) -> CleanHit | None:
    """
    Hallucination / noise filter.

    Rules:
    1. score < 0.7 → drop
    2. box height < 10px → drop
    3. len(text)==1 and (noise glyph or special-only) → drop
    4. mostly ``?`` / non-meaningful junk → drop (long-line OCR failures)
    """
    raw = str(text or "").strip()
    try:
        conf = float(score)
    except (TypeError, ValueError):
        return None
    if conf < _MIN_SCORE:
        return None
    coords = [float(v) for v in list(box_coords)]
    if box_height_px(coords) < _MIN_BOX_HEIGHT_PX:
        return None
    if len(raw) == 1 and (raw in NOISE_SINGLE_CHARS or _SPECIAL_ONLY_RE.match(raw)):
        return None
    if not raw or is_garbage_ocr_text(raw):
        return None
    # Return a copy of coords — never mutate caller's list.
    return {"text": raw, "box": list(coords), "score": conf}


def _pick_best_ocr_text(payload: Any) -> tuple[str, float] | None:
    """Pick best non-empty text from Cloud /predict JSON; prefer meaningful glyphs."""
    if not isinstance(payload, list):
        return None
    best: tuple[str, float, int] | None = None
    for item in payload:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text or is_garbage_ocr_text(text):
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        meaning = _meaningful_char_count(text)
        if best is None:
            best = (text, score, meaning)
            continue
        # Prefer more meaningful chars, then higher score.
        if meaning > best[2] or (meaning == best[2] and score > best[1]):
            best = (text, score, meaning)
    if best is None:
        return None
    return best[0], best[1]


async def post_predict_jpeg(
    session: aiohttp.ClientSession,
    *,
    endpoint: str,
    filename: str,
    content: bytes,
    timeout_s: float,
) -> Any:
    """
    POST JPEG to Cloud Run ``/predict``.

    Prompt 2 builds a Base64 payload; Cloud Run's contract is multipart ``file``.
    Callers pass JPEG bytes produced from that Base64 (``base64.b64decode``).
    """
    timeout = aiohttp.ClientTimeout(total=float(timeout_s))
    form = aiohttp.FormData()
    form.add_field(
        "file",
        content,
        filename=filename,
        content_type="image/jpeg",
    )
    async with session.post(endpoint, data=form, timeout=timeout) as response:
        body = await response.read()
        # Prompt 2: retry only Timeout / HTTP 50x (not 4xx like 429).
        if response.status >= 500:
            raise RetryableHttpError(
                response.status,
                f"OCR HTTP {response.status}: {body[:200]!r}",
            )
        if response.status >= 400:
            raise RuntimeError(f"OCR HTTP {response.status}: {body[:200]!r}")
        try:
            return await response.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"OCR response is not valid JSON: {exc}") from exc


class CloudOCRAnalyzer:
    """
    Prompt 2: local OpenCV sharpen → async Cloud Run PaddleOCR → hallucination filter.

    Concurrency is locked to ``asyncio.Semaphore(4)`` per prompt.
    """

    RetryableHttpError = RetryableHttpError

    def __init__(
        self,
        endpoint_url: str | None = None,
        *,
        concurrency: int | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_delay_s: float = _DEFAULT_RETRY_DELAY_S,
        timeout_seconds: float | None = None,
    ) -> None:
        resolved = endpoint_url if endpoint_url is not None else resolve_ocr_endpoint_url()
        self.endpoint = normalize_predict_endpoint(resolved)
        # Prompt 2 default Semaphore(4); env OCR_ASYNC_CONCURRENCY overrides (local=2).
        self.concurrency = (
            max(1, int(concurrency))
            if concurrency is not None
            else resolve_analyze_concurrency()
        )
        self.max_retries = max(0, int(max_retries))
        self.retry_delay_s = float(retry_delay_s)
        self.timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else resolve_ocr_http_timeout_seconds()
        )

    async def _post_with_retry(
        self,
        session: aiohttp.ClientSession,
        *,
        filename: str,
        content: bytes,
    ) -> Any:
        attempts = self.max_retries + 1
        last_exc: BaseException | None = None
        for attempt in range(attempts):
            try:
                return await post_predict_jpeg(
                    session,
                    endpoint=self.endpoint,
                    filename=filename,
                    content=content,
                    timeout_s=self.timeout_seconds,
                )
            except (asyncio.TimeoutError, RetryableHttpError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                err_msg = str(exc).strip() or type(exc).__name__
                logger.warning(
                    "cloud_ocr_retry attempt=%s/%s err=%s",
                    attempt + 1,
                    attempts,
                    err_msg,
                )
                await asyncio.sleep(self.retry_delay_s)
        assert last_exc is not None
        raise last_exc

    async def _analyze_one(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        item: CropItem,
        index: int,
    ) -> tuple[str, CleanHit] | None:
        async with semaphore:
            try:
                ts = float(item["timestamp"])
                coords_raw = item["original_box_coords"]
                # Preserve caller coords 100% — only convert shape for output.
                quad = original_box_to_quad(coords_raw)
                prepared = item.get("prepared_jpeg")
                if prepared is not None:
                    jpeg_bytes = bytes(prepared)
                else:
                    # Legacy Prompt 2 path: sharpen → JPEG q=95.
                    crop = item["image_crop"]
                    image_b64, _jpeg = preprocess_crop_to_jpeg_b64(crop)
                    jpeg_bytes = base64.b64decode(image_b64)
                payload = await self._post_with_retry(
                    session,
                    filename=f"crop_{index:04d}.jpg",
                    content=jpeg_bytes,
                )
                best = _pick_best_ocr_text(payload)
                if best is None:
                    return None
                text, score = best
                cleaned = clean_ocr_data(text, score, quad)
                if cleaned is None:
                    return None
                # Drop score from public payload shape (prompt example has text+box only).
                public = {"text": cleaned["text"], "box": cleaned["box"]}
                return format_timestamp_key(ts), public
            except Exception as exc:  # noqa: BLE001
                logger.warning("cloud_ocr_item_failed index=%s err=%s", index, exc)
                return None

    async def analyze(self, crops: list[CropItem]) -> GroupedResult:
        """
        Analyze a list of crop dicts.

        Each item: ``timestamp``, ``original_box_coords``, ``image_crop``.
        Returns mapping ``timestamp_key → [{text, box}, ...]``.
        """
        if not crops:
            return {}
        semaphore = asyncio.Semaphore(self.concurrency)
        connector = aiohttp.TCPConnector(limit=self.concurrency)
        grouped: dict[str, list[CleanHit]] = defaultdict(list)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._analyze_one(session, semaphore, item, i)
                for i, item in enumerate(crops)
            ]
            results = await tqdm_asyncio.gather(*tasks, desc="Cloud OCR", total=len(tasks))
        for item in results:
            if item is None:
                continue
            ts_key, hit = item
            grouped[ts_key].append(hit)
        # Stable key order by parsed time.
        ordered = dict(sorted(grouped.items(), key=lambda kv: kv[0]))
        return ordered

    def analyze_sync(self, crops: list[CropItem]) -> GroupedResult:
        """Sync wrapper for scripts / ``__main__``."""
        try:
            return asyncio.run(self.analyze(crops))
        except RuntimeError:
            # Nested loop (rare) — create a fresh loop.
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.analyze(crops))
            finally:
                loop.close()


def load_crop_items_from_ske_dir(ske_dir: str | Path) -> list[CropItem]:
    """
    Build ``CloudOCRAnalyzer`` crop items from a SmartKeyframeExtractor run folder.

    Expects ``summary.json`` + keyframe ``*.jpg``. Crops use
    ``prepare_recognition_crop`` (padded color + CLAHE), not BW Otsu PNGs.
    ``original_box_coords`` stay frame-absolute (unpadded).
    """
    root = Path(ske_dir)
    summary_path = root / "summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"Missing summary.json in {root}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    fps = float(summary.get("fps") or 0.0)
    items: list[CropItem] = []
    for kf in summary.get("keyframes") or []:
        if not isinstance(kf, dict):
            continue
        frame_file = str(kf.get("frame_file") or "").strip()
        if not frame_file:
            continue
        frame_path = root / frame_file
        if not frame_path.is_file():
            logger.warning("ske_frame_missing path=%s", frame_path)
            continue
        frame = cv2.imread(str(frame_path))
        if frame is None:
            logger.warning("ske_frame_read_failed path=%s", frame_path)
            continue
        frame_index = int(kf.get("frame_index") or 0)
        if kf.get("approx_time_s") is not None:
            ts = float(kf["approx_time_s"])
        elif fps > 0:
            ts = float(frame_index) / fps
        else:
            ts = float(frame_index)
        for box in kf.get("boxes") or []:
            if not isinstance(box, dict):
                continue
            try:
                x0 = float(box["x0"])
                y0 = float(box["y0"])
                x1 = float(box["x1"])
                y1 = float(box["y1"])
            except (KeyError, TypeError, ValueError):
                continue
            if x1 <= x0 + 1 or y1 <= y0 + 1:
                continue
            try:
                crop = prepare_recognition_crop(frame, x0, y0, x1, y1)
            except ValueError:
                continue
            items.append(
                {
                    "timestamp": ts,
                    "original_box_coords": [x0, y0, x1, y1],
                    "image_crop": crop,
                    "frame_index": frame_index,
                    "frame_file": frame_file,
                }
            )
    return items


def ske_grouped_to_ocr_payload(
    grouped: GroupedResult,
    *,
    ske_dir: str | Path,
    provider: str = "ske_cloud_ocr",
) -> dict[str, Any]:
    """
    Map SKE crop OCR hits into the Phase-2 ``ocr_payload`` shape
    (normalized xywh boxes per keyframe) used by translate/render.
    """
    root = Path(ske_dir)
    summary_path = root / "summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"Missing summary.json in {root}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    frames_out: list[dict[str, Any]] = []
    for kf in summary.get("keyframes") or []:
        if not isinstance(kf, dict):
            continue
        frame_file = str(kf.get("frame_file") or "").strip()
        if not frame_file:
            continue
        frame_path = root / frame_file
        if kf.get("approx_time_s") is not None:
            ts = float(kf["approx_time_s"])
        else:
            ts = 0.0
        ts_key = format_timestamp_key(ts)
        hits = grouped.get(ts_key) or []
        width = height = 0
        if frame_path.is_file():
            img = cv2.imread(str(frame_path))
            if img is not None:
                height, width = int(img.shape[0]), int(img.shape[1])
        boxes_out: list[dict[str, Any]] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            text = str(hit.get("text") or "").strip()
            quad = hit.get("box") or []
            if len(quad) < 8 or width <= 0 or height <= 0:
                continue
            xs = [float(quad[i]) for i in range(0, 8, 2)]
            ys = [float(quad[i]) for i in range(1, 8, 2)]
            x0, x1 = min(xs), max(xs)
            y0, y1 = min(ys), max(ys)
            bw = max(0.0, x1 - x0)
            bh = max(0.0, y1 - y0)
            boxes_out.append(
                {
                    "x": x0 / float(width),
                    "y": y0 / float(height),
                    "width": bw / float(width),
                    "height": bh / float(height),
                    "text": text,
                    "confidence": float(hit.get("confidence") or 1.0),
                    "vertices": [
                        {"x": xs[0] / float(width), "y": ys[0] / float(height)},
                        {"x": xs[1] / float(width), "y": ys[1] / float(height)},
                        {"x": xs[2] / float(width), "y": ys[2] / float(height)},
                        {"x": xs[3] / float(width), "y": ys[3] / float(height)},
                    ],
                }
            )
        frames_out.append(
            {
                "frame_id": Path(frame_file).stem,
                "path": str(frame_path),
                "time_ms": int(round(ts * 1000.0)),
                "frame_width": width,
                "frame_height": height,
                "raw_box_count": len(hits),
                "filtered_out_count": max(0, len(hits) - len(boxes_out)),
                "boxes": boxes_out,
            }
        )
    return {
        "provider": provider,
        "frame_count": len(frames_out),
        "warnings": [],
        "frames": frames_out,
    }


def export_analyze_result(
    grouped: GroupedResult,
    out_dir: str | Path,
    *,
    meta: dict[str, Any] | None = None,
) -> Path:
    """Write ``result.json`` (+ flat ``texts_by_time.txt``) under ``out_dir``."""
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": dict(meta or {}),
        "timestamp_count": len(grouped),
        "hit_count": sum(len(v) for v in grouped.values()),
        "results": grouped,
    }
    out_json = dest / "result.json"
    out_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines: list[str] = []
    for ts, hits in grouped.items():
        for h in hits:
            lines.append(f"{ts}\t{h.get('text', '')}\t{h.get('box')}")
    (dest / "texts_by_time.txt").write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )
    return out_json


def _dummy_crops() -> list[CropItem]:
    """Synthetic crops with readable glyphs for ``python -m …analyze_ocr`` smoke."""
    crops: list[CropItem] = []
    for i, (ts, label) in enumerate(((0.0, "MEAL 614"), (5.5, "TOFU"), (5.5, "KCAL"))):
        img = np.full((64, 220, 3), 255, dtype=np.uint8)
        cv2.putText(
            img,
            label,
            (12, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        crops.append(
            {
                "timestamp": ts,
                "original_box_coords": [50 + i * 10, 100, 200 + i * 10, 140],
                "image_crop": img,
            }
        )
    return crops


def _parse_arg_value(args: list[str], flag: str) -> str | None:
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args) and not args[i + 1].startswith("-"):
            return args[i + 1]
    prefix = f"{flag}="
    for a in args:
        if a.startswith(prefix):
            return a[len(prefix) :]
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO)
    dry = "--dry" in args or os.environ.get("ANALYZE_OCR_DRY") == "1"
    ske_dir = _parse_arg_value(args, "--from-ske")
    out_dir_arg = _parse_arg_value(args, "--out")
    max_crops_raw = _parse_arg_value(args, "--max-crops")
    max_crops = int(max_crops_raw) if max_crops_raw else None

    if ske_dir:
        crops = load_crop_items_from_ske_dir(ske_dir)
        source = f"ske:{Path(ske_dir).resolve()}"
        print(f"[INFO] loaded_ske_crops={len(crops)} from={ske_dir}")
    else:
        crops = _dummy_crops()
        source = "dummy"
        print(f"[INFO] dummy_crops={len(crops)}")

    if max_crops is not None and max_crops >= 0:
        crops = crops[:max_crops]
        print(f"[INFO] truncated_to max_crops={len(crops)}")

    if dry:
        for i, c in enumerate(crops[:5]):
            b64, jpeg = preprocess_crop_to_jpeg_b64(c["image_crop"])
            quad = original_box_to_quad(c["original_box_coords"])
            print(
                f"  [{i}] ts={format_timestamp_key(float(c['timestamp']))} "
                f"jpeg={len(jpeg)}B b64_len={len(b64)} box={quad}"
            )
        if crops:
            quad = original_box_to_quad(crops[0]["original_box_coords"])
            kept = clean_ocr_data("meal", 0.9, quad)
            dropped = clean_ocr_data("一", 0.99, quad)
            print(f"[INFO] clean keep={kept is not None} drop_noise={dropped is None}")
        print("[OK] dry-run (no OCR HTTP)")
        return 0

    if not crops:
        print("[ERROR] No crops to analyze", file=sys.stderr)
        return 1

    try:
        analyzer = CloudOCRAnalyzer(max_retries=2)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Cannot resolve OCR endpoint: {exc}", file=sys.stderr)
        print("Hint: set OCR_ENDPOINT_URL or re-run with --dry", file=sys.stderr)
        return 1
    print(f"[INFO] endpoint={analyzer.endpoint} concurrency={analyzer.concurrency}")
    try:
        result = analyzer.analyze_sync(crops)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] analyze failed: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(out_dir_arg) if out_dir_arg else (
        Path(__file__).resolve().parents[3] / "tmp_analyze_ocr_run"
        if ske_dir
        else None
    )
    if out_dir is not None:
        out_path = export_analyze_result(
            result,
            out_dir,
            meta={
                "source": source,
                "endpoint": analyzer.endpoint,
                "crop_count": len(crops),
                "concurrency": analyzer.concurrency,
            },
        )
        print(f"[OUT] {out_path}")

    print(f"[OK] timestamps={list(result.keys())} hits={sum(len(v) for v in result.values())}")
    for ts, hits in result.items():
        for h in hits:
            try:
                print(f"  {ts}: text={h['text']!r} box={h['box']}")
            except UnicodeEncodeError:
                print(f"  {ts}: text=<unicode> box={h['box']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
