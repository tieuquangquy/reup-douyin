from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener, urlopen

from src.downloaders.base import AssetDownloader, DownloadedObject
from src.downloaders.errors import DownloadError, DownloadErrorCode, DownloadFailureReason


class HttpAssetDownloader(AssetDownloader):
    def __init__(
        self,
        timeout_seconds: int = 30,
        *,
        chunk_size_bytes: int = 1024 * 1024,
        max_bytes: int = 2_000_000_000,
    ):
        self.timeout_seconds = timeout_seconds
        self.chunk_size_bytes = max(64 * 1024, int(chunk_size_bytes))
        self.max_bytes = max(1, int(max_bytes))

    def fetch(self, url: str) -> DownloadedObject:
        if not url:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Missing source URL")
        try:
            request = Request(url, headers={"User-Agent": "reup-douyin-local/0.1"})
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read()
                if len(content) > self.max_bytes:
                    raise DownloadError(
                        DownloadErrorCode.VALIDATION_FAILED,
                        f"HTTP asset exceeds configured limit ({self.max_bytes} bytes)",
                    )
                mime_type = response.headers.get_content_type()
        except URLError as exc:
            raise DownloadError(DownloadErrorCode.DOWNLOAD_FAILED, f"Download failed: {exc}") from exc
        filename = _filename_from_url(url)
        return DownloadedObject(content=content, mime_type=mime_type, filename=filename)

    def fetch_to_file(
        self,
        url: str,
        destination: str | Path,
        *,
        resume: bool = True,
        on_progress: Callable[[int, int | None], None] | None = None,
        headers: Mapping[str, str] | None = None,
        proxy_url: str | None = None,
    ) -> DownloadedObject:
        """Stream an HTTP object to a resumable staging file.

        ``destination`` is intentionally a staging object, not the authoritative
        storage path.  A caller validates it and promotes it atomically afterwards.
        Servers that ignore Range safely restart the staging object from byte zero.
        """
        if not url:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Missing source URL")
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        resume_state_path = _resume_state_path(destination_path)
        existing_size = destination_path.stat().st_size if resume and destination_path.is_file() else 0
        if existing_size > self.max_bytes:
            destination_path.unlink(missing_ok=True)
            resume_state_path.unlink(missing_ok=True)
            raise DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                f"HTTP partial asset exceeds configured limit ({self.max_bytes} bytes)",
            )
        url_fingerprint = _url_fingerprint(url)
        resource_fingerprint = _resource_fingerprint(url)
        resume_state = _read_resume_state(resume_state_path) if resume and existing_size else None
        if existing_size and resume_state is None:
            # Legacy/orphan partials have no resource identity.  Appending them
            # can produce a valid-looking but corrupted video, so restart.
            destination_path.unlink(missing_ok=True)
            existing_size = 0
        if existing_size and resume_state:
            stored_url_fingerprint = resume_state.get("url_fingerprint")
            stored_resource_fingerprint = resume_state.get("resource_fingerprint")
            validator = resume_state.get("etag") or resume_state.get("last_modified")
            same_full_url = stored_url_fingerprint in {None, url_fingerprint}
            # Signed CDN URLs rotate query credentials while the media path and
            # validator remain stable. Permit that useful resume case only when
            # both a canonical resource identity and an HTTP validator agree;
            # otherwise fail closed and restart from byte zero.
            same_rotated_resource = (
                stored_url_fingerprint not in {None, url_fingerprint}
                and stored_resource_fingerprint == resource_fingerprint
                and isinstance(validator, str)
                and bool(validator.strip())
            )
            if not same_full_url and not same_rotated_resource:
                destination_path.unlink(missing_ok=True)
                resume_state_path.unlink(missing_ok=True)
                existing_size = 0
                resume_state = None
        request_headers = {"User-Agent": "reup-douyin-local/0.1", **dict(headers or {})}
        if existing_size > 0:
            request_headers["Range"] = f"bytes={existing_size}-"
            validator = (resume_state or {}).get("etag") or (resume_state or {}).get("last_modified")
            if isinstance(validator, str) and validator.strip():
                request_headers["If-Range"] = validator
        request = Request(url, headers=request_headers)

        try:
            if proxy_url or request.headers.get("Cookie"):
                handlers = [_CredentialSafeRedirectHandler()]
                if proxy_url:
                    handlers.insert(0, ProxyHandler({"http": proxy_url, "https": proxy_url}))
                response_context = build_opener(*handlers).open(request, timeout=self.timeout_seconds)
            else:
                response_context = urlopen(request, timeout=self.timeout_seconds)
        except HTTPError as exc:
            if exc.code == 416 and existing_size > 0:
                total = _range_not_satisfiable_total(exc.headers.get("Content-Range"))
                if total is not None and total == existing_size:
                    if total > self.max_bytes:
                        destination_path.unlink(missing_ok=True)
                        resume_state_path.unlink(missing_ok=True)
                        raise DownloadError(
                            DownloadErrorCode.VALIDATION_FAILED,
                            f"HTTP asset exceeds configured limit ({self.max_bytes} bytes)",
                        ) from exc
                    if on_progress:
                        on_progress(existing_size, total)
                    resume_state_path.unlink(missing_ok=True)
                    return DownloadedObject(
                        content=None,
                        mime_type=exc.headers.get_content_type(),
                        filename=_filename_from_url(url),
                        local_path=str(destination_path),
                        size_bytes=existing_size,
                    )
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"Download failed: HTTP {exc.code}",
                reason=(
                    DownloadFailureReason.SIGNED_URL_EXPIRED
                    if exc.code in {401, 403, 410}
                    else DownloadFailureReason.NETWORK_TRANSIENT
                ),
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"Download failed: {exc}",
                reason=DownloadFailureReason.NETWORK_TRANSIENT,
            ) from exc

        try:
            with response_context as response:
                status = int(getattr(response, "status", 0) or response.getcode() or 0)
                if status not in {200, 206}:
                    raise DownloadError(
                        DownloadErrorCode.DOWNLOAD_FAILED,
                        f"Download failed: HTTP {status}",
                        reason=(
                            DownloadFailureReason.SIGNED_URL_EXPIRED
                            if status in {401, 403, 410}
                            else DownloadFailureReason.NETWORK_TRANSIENT
                        ),
                    )
                mime_type = response.headers.get_content_type()
                _validate_stream_media_type(url, mime_type)
                append = bool(existing_size and status == 206)
                if append:
                    range_start = _range_start(response.headers.get("Content-Range"))
                    response_validator = _response_validator(response.headers)
                    expected_validator = (resume_state or {}).get("etag") or (resume_state or {}).get(
                        "last_modified"
                    )
                    if (
                        range_start != existing_size
                        or (
                            expected_validator
                            and response_validator
                            and expected_validator != response_validator
                        )
                        or (expected_validator and not response_validator)
                    ):
                        # A stale CDN response must never be appended to a partial
                        # file from another signed URL. Restart safely from byte 0.
                        close_response = getattr(response, "close", None)
                        if callable(close_response):
                            close_response()
                        return self.fetch_to_file(
                            url,
                            destination_path,
                            resume=False,
                            on_progress=on_progress,
                            headers=headers,
                            proxy_url=proxy_url,
                        )
                bytes_done = existing_size if append else 0
                total = _response_total_bytes(response.headers, status=status, bytes_done=bytes_done)
                if total is not None and total > self.max_bytes:
                    raise DownloadError(
                        DownloadErrorCode.VALIDATION_FAILED,
                        f"HTTP asset exceeds configured limit ({self.max_bytes} bytes)",
                    )
                _write_resume_state(
                    resume_state_path,
                    {
                        "url_fingerprint": url_fingerprint,
                        "resource_fingerprint": resource_fingerprint,
                        "etag": _header(response.headers, "ETag"),
                        "last_modified": _header(response.headers, "Last-Modified"),
                        "total": total,
                    },
                )
                mode = "ab" if append else "wb"
                with destination_path.open(mode) as handle:
                    while True:
                        chunk = response.read(self.chunk_size_bytes)
                        if not chunk:
                            break
                        handle.write(chunk)
                        bytes_done += len(chunk)
                        if bytes_done > self.max_bytes:
                            raise DownloadError(
                                DownloadErrorCode.VALIDATION_FAILED,
                                f"HTTP asset exceeds configured limit ({self.max_bytes} bytes)",
                            )
                        if on_progress:
                            on_progress(bytes_done, total)
                    handle.flush()
                    os.fsync(handle.fileno())
        except DownloadError as exc:
            if exc.code == DownloadErrorCode.VALIDATION_FAILED:
                try:
                    destination_path.unlink(missing_ok=True)
                    resume_state_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        except (URLError, TimeoutError, OSError) as exc:
            # Keep the staging file: the next retry can continue with HTTP Range.
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"Download interrupted: {exc}",
                reason=DownloadFailureReason.NETWORK_TRANSIENT,
            ) from exc

        final_size = destination_path.stat().st_size if destination_path.exists() else 0
        if final_size <= 0:
            raise DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                "HTTP downloader produced an empty file",
                reason=DownloadFailureReason.MEDIA_CORRUPT,
            )
        if total is not None and final_size != total:
            if final_size > total:
                destination_path.unlink(missing_ok=True)
                resume_state_path.unlink(missing_ok=True)
                raise DownloadError(
                    DownloadErrorCode.VALIDATION_FAILED,
                    f"HTTP asset size mismatch: received {final_size}, expected {total} bytes",
                    reason=DownloadFailureReason.MEDIA_CORRUPT,
                )
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"Download interrupted: received {final_size} of {total} bytes",
                reason=DownloadFailureReason.NETWORK_TRANSIENT,
            )
        if on_progress:
            on_progress(final_size, total or final_size)
        resume_state_path.unlink(missing_ok=True)
        return DownloadedObject(
            content=None,
            mime_type=mime_type,
            filename=_filename_from_url(url),
            local_path=str(destination_path),
            size_bytes=final_size,
        )


def _filename_from_url(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    return path.rsplit("/", 1)[-1] or None


def _validate_stream_media_type(url: str, mime_type: str | None) -> None:
    normalized = (mime_type or "").lower()
    url_path = urlparse(url).path.lower()
    if url_path.endswith((".m3u8", ".mpd")) or normalized in {
        "application/vnd.apple.mpegurl",
        "application/x-mpegurl",
        "application/dash+xml",
    }:
        raise DownloadError(
            DownloadErrorCode.VALIDATION_FAILED,
            "HLS/DASH manifest requires yt-dlp/ffmpeg media assembly; refusing to persist manifest bytes as video",
        )
    if normalized.startswith("text/") or normalized in {"application/json", "application/xml"}:
        raise DownloadError(
            DownloadErrorCode.VALIDATION_FAILED,
            f"HTTP source returned non-video content type: {normalized or 'unknown'}",
        )


def _response_total_bytes(headers, *, status: int, bytes_done: int) -> int | None:
    content_range = headers.get("Content-Range")
    if status == 206 and content_range and "/" in content_range:
        raw_total = content_range.rsplit("/", 1)[-1].strip()
        if raw_total.isdigit():
            return int(raw_total)
    content_length = headers.get("Content-Length")
    if content_length and str(content_length).isdigit():
        length = int(content_length)
        return bytes_done + length if status == 206 else length
    return None


def _range_not_satisfiable_total(content_range: str | None) -> int | None:
    if not content_range or "/" not in content_range:
        return None
    raw_total = content_range.rsplit("/", 1)[-1].strip()
    return int(raw_total) if raw_total.isdigit() else None


def _range_start(content_range: str | None) -> int | None:
    if not content_range or not content_range.lower().startswith("bytes ") or "-" not in content_range:
        return None
    raw = content_range[6:].split("-", 1)[0].strip()
    return int(raw) if raw.isdigit() else None


def _resume_state_path(destination: Path) -> Path:
    return destination.with_name(f"{destination.name}.resume.json")


def _url_fingerprint(url: str) -> str:
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()


# Query parameters used by common Douyin/TOS signed URLs. They identify the
# authorization window, not the underlying media object. They are removed only
# for the secondary resource fingerprint; the full URL fingerprint remains the
# primary identity and is still required when no HTTP validator is available.
_VOLATILE_SIGNED_QUERY_KEYS = frozenset(
    {
        "expire",
        "expires",
        "token",
        "signature",
        "auth_key",
        "x-signature",
        "x-expires",
        "x-tos-date",
        "x-tos-credential",
        "x-tos-security-token",
        "x-tos-signature",
        "x-tos-signedheaders",
    }
)


def _resource_fingerprint(url: str) -> str:
    """Fingerprint media identity while ignoring rotating CDN credentials."""
    parsed = urlsplit((url or "").strip())
    stable_query = [
        (key.lower(), value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _VOLATILE_SIGNED_QUERY_KEYS
        and not key.lower().startswith("x-amz-")
        and not key.lower().startswith("x-tos-")
    ]
    canonical = urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            urlencode(sorted(stable_query)),
            "",
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _header(headers, name: str) -> str | None:
    try:
        value = headers.get(name)
    except Exception:
        return None
    value = str(value or "").strip()
    return value or None


def _response_validator(headers) -> str | None:
    return _header(headers, "ETag") or _header(headers, "Last-Modified")


def _read_resume_state(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_resume_state(path: Path, value: dict) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.part")
    try:
        temp.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


class _CredentialSafeRedirectHandler(HTTPRedirectHandler):
    """Strip credential headers when urllib follows a cross-host redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old_url = urlparse(req.full_url)
        new_url = urlparse(newurl)
        old_host = (old_url.hostname or "").lower().rstrip(".")
        new_host = (new_url.hostname or "").lower().rstrip(".")
        scheme_downgrade = old_url.scheme.lower() == "https" and new_url.scheme.lower() != "https"
        if old_host and new_host and (old_host != new_host or scheme_downgrade):
            for key in ("Cookie", "Authorization", "Proxy-Authorization", "If-Range"):
                redirected.remove_header(key)
        return redirected
