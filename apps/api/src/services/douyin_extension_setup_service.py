from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from src.schemas.douyin_extension import (
    DouyinExtensionHandshakeRequest,
    DouyinExtensionManagerHistoryItem,
    DouyinExtensionManagerHistoryResponse,
    DouyinExtensionStatusResponse,
)

EXPECTED_EXTENSION_VERSION = "0.1.0"
SUPPORTED_EXTENSION_VERSIONS = [EXPECTED_EXTENSION_VERSION]
STALE_AFTER_SECONDS = 120
DOWNLOAD_URL = "/douyin-extension/download"
_EXTENSION_DIST_RELATIVE_PATH = Path("apps/extension-douyin-capture/dist")


_HISTORY_LIMIT = 20


class DouyinExtensionSetupError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class DouyinExtensionHandshakeSnapshot:
    install_id: str
    extension_id: str | None
    extension_version: str
    browser_family: str
    api_base_url: str | None
    client_time: datetime | None
    received_at: datetime


_last_handshake: DouyinExtensionHandshakeSnapshot | None = None
_manager_history: list[DouyinExtensionManagerHistoryItem] = []


class DouyinExtensionSetupService:
    def __init__(self, *, now: datetime | None = None, extension_dist_dir: Path | None = None):
        self.now = now or datetime.now(UTC)
        self.extension_dist_dir = extension_dist_dir or _resolve_extension_dist_dir()

    def record_handshake(self, request: DouyinExtensionHandshakeRequest) -> DouyinExtensionStatusResponse:
        global _last_handshake
        _last_handshake = DouyinExtensionHandshakeSnapshot(
            install_id=request.install_id,
            extension_id=request.extension_id,
            extension_version=request.extension_version,
            browser_family=request.browser_family,
            api_base_url=request.api_base_url,
            client_time=request.client_time,
            received_at=self.now,
        )
        status = self.status()
        self.record_history_event(
            event_type="handshake",
            status="success",
            recommended_next_action=status.recommended_next_action,
            recommended_next_action_label=status.recommended_next_action_label,
        )
        return status

    def status(self) -> DouyinExtensionStatusResponse:
        snapshot = _last_handshake
        download_available = self.download_available()
        if snapshot is None:
            return DouyinExtensionStatusResponse(
                status="not_installed_or_not_connected",
                connected=False,
                stale_after_seconds=STALE_AFTER_SECONDS,
                backend_checked_at=self.now,
                backend_expected_extension_version=EXPECTED_EXTENSION_VERSION,
                backend_supported_extension_versions=SUPPORTED_EXTENSION_VERSIONS,
                version_status="unknown",
                compatible=False,
                recommended_next_action="download_extension" if download_available else "build_extension",
                recommended_next_action_label="Download and install the extension manually." if download_available else "Build the extension before installing it.",
                operator_message="No Douyin extension handshake has reached this backend process yet.",
                download_available=download_available,
                download_url=DOWNLOAD_URL,
            )

        version_status = "compatible" if snapshot.extension_version in SUPPORTED_EXTENSION_VERSIONS else "version_mismatch"
        is_stale = self.now - snapshot.received_at > timedelta(seconds=STALE_AFTER_SECONDS)
        if version_status == "version_mismatch":
            status = "version_mismatch"
            connected = False
            recommended_next_action = "update_extension"
            recommended_next_action_label = "Update or reload the extension so its version matches the backend."
            operator_message = "The extension reached the backend, but its version is not compatible with this backend."
        elif is_stale:
            status = "stale_connection"
            connected = False
            recommended_next_action = "open_extension_and_check_connection"
            recommended_next_action_label = "Open the extension popup and run the connection check again."
            operator_message = "The extension connected before, but the last ping is stale."
        else:
            status = "connected"
            connected = True
            recommended_next_action = "open_douyin_and_capture"
            recommended_next_action_label = "Open Douyin and use the extension to detect or capture the current page."
            operator_message = "The Douyin extension is connected and compatible."

        return DouyinExtensionStatusResponse(
            status=status,
            connected=connected,
            install_id=snapshot.install_id,
            extension_id=snapshot.extension_id,
            extension_version=snapshot.extension_version,
            browser_family=snapshot.browser_family,  # type: ignore[arg-type]
            api_base_url=snapshot.api_base_url,
            last_seen_at=snapshot.received_at,
            stale_after_seconds=STALE_AFTER_SECONDS,
            backend_checked_at=self.now,
            backend_expected_extension_version=EXPECTED_EXTENSION_VERSION,
            backend_supported_extension_versions=SUPPORTED_EXTENSION_VERSIONS,
            version_status=version_status,
            compatible=version_status == "compatible",
            recommended_next_action=recommended_next_action,  # type: ignore[arg-type]
            recommended_next_action_label=recommended_next_action_label,
            operator_message=operator_message,
            download_available=download_available,
            download_url=DOWNLOAD_URL,
        )

    def history(self, *, limit: int = _HISTORY_LIMIT) -> DouyinExtensionManagerHistoryResponse:
        safe_limit = max(1, min(limit, _HISTORY_LIMIT))
        items = list(_manager_history[:safe_limit])
        return DouyinExtensionManagerHistoryResponse(items=items, total_count=len(_manager_history))

    def record_history_event(
        self,
        *,
        event_type: str,
        status: str,
        page_type: str | None = None,
        page_url: str | None = None,
        page_title: str | None = None,
        supported_capture: bool | None = None,
        imported_profile_count: int = 0,
        videos_discovered_count: int = 0,
        videos_created_count: int = 0,
        videos_updated_count: int = 0,
        candidates_matched_count: int = 0,
        error_code: str | None = None,
        error_message: str | None = None,
        warning: str | None = None,
        recommended_next_action: str | None = None,
        recommended_next_action_label: str | None = None,
        diagnostics_id: str | None = None,
    ) -> DouyinExtensionManagerHistoryItem:
        item = DouyinExtensionManagerHistoryItem(
            event_id=str(uuid4()),
            event_type=event_type,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            created_at=self.now,
            page_type=page_type,  # type: ignore[arg-type]
            page_url=page_url,
            page_title=page_title,
            supported_capture=supported_capture,
            imported_profile_count=imported_profile_count,
            videos_discovered_count=videos_discovered_count,
            videos_created_count=videos_created_count,
            videos_updated_count=videos_updated_count,
            candidates_matched_count=candidates_matched_count,
            error_code=error_code,
            error_message=_truncate_message(error_message),
            warning=_truncate_message(warning),
            recommended_next_action=recommended_next_action,
            recommended_next_action_label=recommended_next_action_label,
            diagnostics_id=diagnostics_id,
        )
        _manager_history.insert(0, item)
        del _manager_history[_HISTORY_LIMIT:]
        return item

    def record_detect_result(self, response: Any) -> None:
        self.record_history_event(
            event_type="detect",
            status="success",
            page_type=getattr(response, "detected_page_type", None),
            page_url=getattr(response, "page_url", None),
            page_title=getattr(response, "title", None),
            supported_capture=getattr(response, "supported_capture", None),
            recommended_next_action=getattr(response, "recommended_action", None),
            recommended_next_action_label=getattr(response, "recommended_action_label", None),
            diagnostics_id=getattr(response, "diagnostics_id", None),
        )

    def record_capture_result(self, response: Any) -> None:
        self.record_history_event(
            event_type="capture",
            status="success",
            page_type=getattr(response, "detected_page_type", None),
            page_url=getattr(response, "current_page_url", None),
            page_title=getattr(response, "current_page_title", None),
            imported_profile_count=1 if getattr(response, "source_profile_id", None) else 0,
            videos_discovered_count=getattr(response, "videos_discovered_count", 0),
            videos_created_count=getattr(response, "videos_created_count", 0),
            videos_updated_count=getattr(response, "videos_updated_count", 0),
            candidates_matched_count=getattr(response, "candidates_matched_count", 0),
            warning=getattr(response, "warning", None),
            recommended_next_action="open_douyin_and_capture",
            recommended_next_action_label="Review imported candidates or continue with another Douyin page.",
            diagnostics_id=getattr(response, "diagnostics_id", None),
        )

    def record_failure(self, *, event_type: str, error_code: str, error_message: str, page_type: str | None = None, diagnostics_id: str | None = None) -> None:
        self.record_history_event(
            event_type=event_type,
            status="failed",
            page_type=page_type,
            error_code=error_code,
            error_message=error_message,
            recommended_next_action=_recommended_action_for_error(error_code, event_type=event_type),
            recommended_next_action_label=_recommended_label_for_error(error_code, event_type=event_type),
            diagnostics_id=diagnostics_id,
        )

    def download_available(self) -> bool:
        try:
            self._packageable_dist_files()
        except DouyinExtensionSetupError:
            return False
        return True

    def build_download_zip(self) -> tuple[bytes, str]:
        files = self._packageable_dist_files()
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(self.extension_dist_dir).as_posix())
        filename = f"reup-douyin-extension-{EXPECTED_EXTENSION_VERSION}.zip"
        return buffer.getvalue(), filename

    def _packageable_dist_files(self) -> list[Path]:
        if not self.extension_dist_dir.exists() or not self.extension_dist_dir.is_dir():
            raise DouyinExtensionSetupError(
                "extension_build_missing",
                "Extension build is missing. Run npm run extension:build, then try the download again.",
            )
        files = sorted(path for path in self.extension_dist_dir.rglob("*") if path.is_file())
        if not files:
            raise DouyinExtensionSetupError(
                "extension_build_empty",
                "Extension build directory is empty. Run npm run extension:build, then try the download again.",
            )
        return files



def reset_douyin_extension_setup_state() -> None:
    global _last_handshake
    _last_handshake = None
    _manager_history.clear()



def _resolve_extension_dist_dir() -> Path:
    return Path(__file__).resolve().parents[4] / _EXTENSION_DIST_RELATIVE_PATH


def _truncate_message(value: str | None, *, max_length: int = 300) -> str | None:
    if value is None:
        return None
    return value if len(value) <= max_length else f"{value[: max_length - 1]}…"


def _recommended_action_for_error(error_code: str, *, event_type: str) -> str:
    if "challenge" in error_code:
        return "open_douyin_and_capture"
    if "login" in error_code:
        return "open_douyin_and_capture"
    if "unsupported" in error_code or "not_capturable" in error_code:
        return "detect_current_page"
    if event_type == "detect":
        return "detect_current_page"
    return "capture_current_page"


def _recommended_label_for_error(error_code: str, *, event_type: str) -> str:
    if "challenge" in error_code:
        return "Solve the Douyin challenge in the browser, then retry."
    if "login" in error_code:
        return "Log in to Douyin in the browser, then retry."
    if "unsupported" in error_code or "not_capturable" in error_code:
        return "Open a supported Douyin profile, feed, or video page and detect again."
    if event_type == "detect":
        return "Update the page snapshot and run Detect current page again."
    return "Review the capture inputs and run Capture current page again."
