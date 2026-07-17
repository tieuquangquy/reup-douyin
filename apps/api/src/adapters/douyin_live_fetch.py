from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.parse import urljoin, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from src.adapters.douyin import DouyinProfileAdapter
from src.adapters.errors import SourceAdapterError, SourceAdapterErrorCode


HttpGet = Callable[[str], str]
BrowserFetch = Callable[[str], dict]
HTTP_TO_BROWSER_FALLBACK_CODES = {
    "parse_zero_videos",
    "parse_failed",
    "blocked_response",
    "login_required",
}


@dataclass(frozen=True)
class DouyinLiveFetchConfig:
    user_agent: str
    session_cookie: str | None = None
    proxy_url: str | None = None
    timeout_seconds: float = 15.0
    max_videos: int = 50


@dataclass(frozen=True)
class DouyinRenderedPageProbe:
    available: bool
    status: str
    reason: str
    title: str | None = None
    page_url: str | None = None
    video_link_count: int = 0


class DouyinLiveFetchClient:
    """Fetches Douyin profile data through browser profile or legacy HTTP fallback.

    This client intentionally stays transport-only. Persistence and candidate
    creation remain in SourceIngestService and CandidateEvaluationService.
    """

    def __init__(
        self,
        config: DouyinLiveFetchConfig,
        *,
        http_get: HttpGet | None = None,
        browser_fetch: BrowserFetch | None = None,
        prefer_browser_profile: bool = False,
        allow_http_fallback: bool = False,
    ):
        self.config = config
        self._http_get = http_get or self._default_http_get
        self._browser_fetch = browser_fetch
        self._prefer_browser_profile = prefer_browser_profile
        self._allow_http_fallback = allow_http_fallback

    def __call__(self, profile_url: str) -> dict:
        browser_unavailable_metadata: dict | None = None
        browser_attempted = False
        if self._prefer_browser_profile and self._browser_fetch is not None:
            try:
                browser_attempted = True
                return self._finalize_payload(
                    self._browser_fetch(profile_url),
                    profile_url=profile_url,
                    fetch_execution_path="browser_profile",
                )
            except SourceAdapterError as exc:
                if not self._allow_http_fallback or not self._should_http_fallback(exc.raw_payload):
                    raise
                if isinstance(exc.raw_payload, dict):
                    browser_unavailable_metadata = exc.raw_payload.get("metadata") if isinstance(exc.raw_payload.get("metadata"), dict) else None

        html = self.fetch_html(profile_url)
        payload = extract_profile_payload_from_html(
            html,
            profile_url=profile_url,
            max_videos=self.config.max_videos,
        )
        if browser_unavailable_metadata is not None:
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            metadata["browser_profile_available"] = False
            metadata["browser_profile_unavailable_reason"] = browser_unavailable_metadata.get("browser_context_reason") or browser_unavailable_metadata.get("blocked_reason")
            metadata["browser_context_status"] = browser_unavailable_metadata.get("browser_context_status")
            metadata["browser_context_reason"] = browser_unavailable_metadata.get("browser_context_reason")
            metadata["http_fallback_attempted"] = True
            metadata["http_fallback_reason"] = "browser_profile_unavailable"
            payload["metadata"] = metadata
        try:
            payload = self._finalize_payload(
                payload,
                profile_url=profile_url,
                fetch_execution_path="http_html",
            )
        except SourceAdapterError as exc:
            if self._should_browser_fallback_from_http(exc.raw_payload) and self._browser_fetch is not None and not browser_attempted:
                return self._fetch_with_browser_fallback(
                    profile_url,
                    http_raw_payload=exc.raw_payload,
                )
            raise
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        response_classification = (
            metadata.get("response_classification")
            if isinstance(metadata.get("response_classification"), dict)
            else None
        )
        if (
            self._browser_fetch is not None
            and response_classification is not None
            and response_classification.get("code") in HTTP_TO_BROWSER_FALLBACK_CODES
            and not browser_attempted
        ):
            return self._fetch_with_browser_fallback(profile_url, http_raw_payload=payload)
        return payload

    def _finalize_payload(
        self,
        payload: dict,
        *,
        profile_url: str,
        fetch_execution_path: str,
        fallback_from_execution_path: str | None = None,
    ) -> dict:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        metadata.update(self._strategy_metadata())
        metadata["fetch_execution_path"] = fetch_execution_path
        metadata["final_execution_path_used"] = fetch_execution_path
        metadata["http_shell_detected"] = fetch_execution_path == "http_html" and metadata.get("response_shape") == "html_shell"
        if fetch_execution_path in {"browser_profile", "http_then_browser_fallback"}:
            metadata["browser_profile_available"] = True
        metadata.setdefault("browser_fallback_attempted", fetch_execution_path == "http_then_browser_fallback")
        metadata.setdefault("http_fallback_attempted", False)
        if fallback_from_execution_path:
            metadata["fallback_from_execution_path"] = fallback_from_execution_path
        payload["metadata"] = metadata
        if not payload.get("videos"):
            classification = None
            if fetch_execution_path == "http_html" and metadata.get("response_shape") == "html_shell":
                probe = self._probe_rendered_profile_page(profile_url)
                metadata["browser_probe"] = {
                    "available": probe.available,
                    "status": probe.status,
                    "reason": probe.reason,
                    "title": probe.title,
                    "page_url": probe.page_url,
                    "video_link_count": probe.video_link_count,
                }
                classification = classify_zero_video_payload(payload, probe=probe)
            if classification is None:
                classification = classify_zero_video_payload(payload)
            if classification is not None:
                metadata["response_classification"] = classification
                payload["metadata"] = metadata
                if classification.get("result") != "warning":
                    raise SourceAdapterError(
                        SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                        classification["message"],
                        raw_payload=payload,
                    )
        if not payload.get("profile") and not payload.get("videos"):
            raise SourceAdapterError(
                SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                "Douyin live fetch did not expose profile/video metadata. The request may require a valid session cookie, proxy, or manual fallback.",
                raw_payload=payload,
            )
        return payload

    def _should_http_fallback(self, raw_payload: dict | None) -> bool:
        if not isinstance(raw_payload, dict):
            return False
        metadata = raw_payload.get("metadata") if isinstance(raw_payload.get("metadata"), dict) else {}
        response_classification = (
            metadata.get("response_classification")
            if isinstance(metadata.get("response_classification"), dict)
            else None
        )
        if response_classification is None:
            return False
        return response_classification.get("code") in {"browser_profile_unavailable", "browser_context_unavailable"}

    def _strategy_metadata(self) -> dict:
        if self._prefer_browser_profile and self._browser_fetch is not None:
            return {
                "strategy_policy": "browser_primary",
                "primary_execution_path": "browser_profile",
                "legacy_http_fallback_allowed": self._allow_http_fallback,
            }
        if self._browser_fetch is not None:
            return {
                "strategy_policy": "http_primary_with_browser_fallback",
                "primary_execution_path": "http_html",
                "legacy_http_fallback_allowed": self._allow_http_fallback,
            }
        return {
            "strategy_policy": "http_only",
            "primary_execution_path": "http_html",
            "legacy_http_fallback_allowed": self._allow_http_fallback,
        }

    def _should_browser_fallback_from_http(self, raw_payload: dict | None) -> bool:
        if not isinstance(raw_payload, dict):
            return False
        metadata = raw_payload.get("metadata") if isinstance(raw_payload.get("metadata"), dict) else {}
        response_classification = (
            metadata.get("response_classification")
            if isinstance(metadata.get("response_classification"), dict)
            else None
        )
        if response_classification is None:
            return False
        return response_classification.get("code") in HTTP_TO_BROWSER_FALLBACK_CODES

    def _fetch_with_browser_fallback(self, profile_url: str, *, http_raw_payload: dict | None) -> dict:
        if self._browser_fetch is None:
            if isinstance(http_raw_payload, dict):
                metadata = http_raw_payload.get("metadata") if isinstance(http_raw_payload.get("metadata"), dict) else {}
                metadata["browser_fallback_attempted"] = False
                http_raw_payload["metadata"] = metadata
            raise SourceAdapterError(
                SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                "HTTP fetch needed browser fallback, but no browser-profile fetch callback was available.",
                raw_payload=http_raw_payload,
            )

        http_metadata = http_raw_payload.get("metadata") if isinstance(http_raw_payload, dict) and isinstance(http_raw_payload.get("metadata"), dict) else {}
        http_response_classification = (
            http_metadata.get("response_classification")
            if isinstance(http_metadata.get("response_classification"), dict)
            else None
        )
        try:
            browser_payload = self._finalize_payload(
                self._browser_fetch(profile_url),
                profile_url=profile_url,
                fetch_execution_path="http_then_browser_fallback",
                fallback_from_execution_path="http_html",
            )
        except SourceAdapterError as exc:
            if isinstance(exc.raw_payload, dict):
                browser_metadata = exc.raw_payload.get("metadata") if isinstance(exc.raw_payload.get("metadata"), dict) else {}
                browser_metadata["fallback_from_execution_path"] = "http_html"
                browser_metadata["http_response_classification"] = http_response_classification
                browser_metadata["browser_fallback_attempted"] = True
                browser_metadata["http_shell_detected"] = http_metadata.get("response_shape") == "html_shell"
                exc.raw_payload["metadata"] = browser_metadata
            raise
        browser_metadata = browser_payload.get("metadata") if isinstance(browser_payload.get("metadata"), dict) else {}
        browser_metadata["http_response_classification"] = http_response_classification
        browser_metadata["browser_fallback_attempted"] = True
        browser_metadata["http_shell_detected"] = http_metadata.get("response_shape") == "html_shell"
        browser_payload["metadata"] = browser_metadata
        return browser_payload

    def fetch_html(self, url: str) -> str:
        return self._http_get(url)

    def _default_http_get(self, profile_url: str) -> str:
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if self.config.session_cookie:
            headers["Cookie"] = self.config.session_cookie

        opener = build_opener()
        if self.config.proxy_url:
            opener = build_opener(ProxyHandler({"http": self.config.proxy_url, "https": self.config.proxy_url}))

        request = Request(profile_url, headers=headers, method="GET")
        try:
            with opener.open(request, timeout=self.config.timeout_seconds) as response:
                content = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return content.decode(charset, errors="replace")
        except HTTPError as exc:
            if exc.code == 429:
                raise SourceAdapterError(
                    SourceAdapterErrorCode.RATE_LIMITED,
                    "Douyin live fetch was rate limited. Try a proxy/session cookie or use already-ingested fallback data.",
                ) from exc
            raise SourceAdapterError(
                SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                f"Douyin live fetch failed with HTTP {exc.code}.",
            ) from exc
        except URLError as exc:
            raise SourceAdapterError(
                SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                f"Douyin live fetch network error: {exc.reason}",
            ) from exc

    def _probe_rendered_profile_page(self, profile_url: str) -> DouyinRenderedPageProbe:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return DouyinRenderedPageProbe(False, "unavailable", "playwright_not_installed")

        browser = None
        context = None
        try:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(channel="chrome", headless=True)
                except Exception:
                    browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.config.user_agent)
                cookies = _cookies_from_cookie_header(self.config.session_cookie)
                if cookies:
                    context.add_cookies(cookies)
                page = context.new_page()
                page.goto(profile_url, wait_until="domcontentloaded", timeout=30_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                title = (page.title() or "").strip()
                try:
                    body_text = page.locator("body").inner_text(timeout=5_000).strip().lower()
                except Exception:
                    body_text = ""
                page_url = page.url
                try:
                    video_link_count = int(
                        page.eval_on_selector_all(
                            'a[href*="/video/"]',
                            "els => els.length",
                        )
                    )
                except Exception:
                    video_link_count = 0
                lowered_title = title.lower()
                if _looks_like_challenge_surface(lowered_title, body_text, page_url):
                    return DouyinRenderedPageProbe(
                        True,
                        "blocked",
                        "browser_probe_detected_challenge_page",
                        title=title or None,
                        page_url=page_url,
                        video_link_count=video_link_count,
                    )
                if _looks_like_login_surface(lowered_title, body_text, page_url):
                    return DouyinRenderedPageProbe(
                        True,
                        "login_required",
                        "browser_probe_detected_login_required",
                        title=title or None,
                        page_url=page_url,
                        video_link_count=video_link_count,
                    )
                if video_link_count > 0:
                    return DouyinRenderedPageProbe(
                        True,
                        "rendered_videos_present",
                        "browser_probe_found_rendered_video_links",
                        title=title or None,
                        page_url=page_url,
                        video_link_count=video_link_count,
                    )
                return DouyinRenderedPageProbe(
                    True,
                    "no_rendered_videos",
                    "browser_probe_found_no_rendered_video_links",
                    title=title or None,
                    page_url=page_url,
                    video_link_count=video_link_count,
                )
        except Exception as exc:
            return DouyinRenderedPageProbe(False, "probe_failed", f"browser_probe_failed:{exc.__class__.__name__}")
        finally:
            try:
                if context is not None:
                    context.close()
            except Exception:
                pass
            try:
                if browser is not None:
                    browser.close()
            except Exception:
                pass


def extract_profile_payload_from_html(html: str, *, profile_url: str, max_videos: int = 50) -> dict:
    documents = list(_embedded_json_documents(html))
    profile = _find_profile(documents) or {}
    videos = _find_videos(documents, max_videos=max_videos)
    identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)

    normalized_profile = {
        "sec_uid": profile.get("sec_uid") or profile.get("uid") or profile.get("id") or identity.source_profile_external_id,
        "display_name": profile.get("display_name") or profile.get("nickname") or profile.get("name"),
        "nickname": profile.get("nickname") or profile.get("display_name") or profile.get("name"),
        "unique_id": profile.get("unique_id") or profile.get("short_id") or identity.handle,
        "follower_count": _first_present(profile, "follower_count", "mplatform_followers_count", "fans_count"),
        "following_count": _first_present(profile, "following_count", "following"),
    }
    return {
        "profile": {key: value for key, value in normalized_profile.items() if value is not None},
        "videos": videos,
        "metadata": {
            "source": "douyin_live_html",
            "embedded_document_count": len(documents),
            "extracted_at": datetime.now(UTC).isoformat(),
            "response_shape": "embedded_payload" if documents else "html_shell",
            "profile_payload_present": bool(profile),
            "video_candidate_count": len(videos),
        },
    }


def extract_profile_payload_from_browser_artifacts(
    *,
    html: str | None,
    profile_url: str,
    response_documents: list[dict | list] | None = None,
    video_links: list[str] | None = None,
    page_title: str | None = None,
    page_url: str | None = None,
    max_videos: int = 50,
) -> dict:
    html_documents = list(_embedded_json_documents(html or ""))
    network_documents = [item for item in (response_documents or []) if isinstance(item, (dict, list))]
    documents = [*html_documents, *network_documents]
    profile = _find_profile(documents) or {}
    videos = _find_videos(documents, max_videos=max_videos)
    parser_strategy = "browser_response_documents" if videos and network_documents else "browser_rendered_html"
    if not videos:
        videos = _videos_from_rendered_links(video_links or [], max_videos=max_videos)
        if videos:
            parser_strategy = "browser_dom_video_links"

    identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
    normalized_profile = {
        "sec_uid": profile.get("sec_uid") or profile.get("uid") or profile.get("id") or identity.source_profile_external_id,
        "display_name": profile.get("display_name") or profile.get("nickname") or profile.get("name"),
        "nickname": profile.get("nickname") or profile.get("display_name") or profile.get("name"),
        "unique_id": profile.get("unique_id") or profile.get("short_id") or identity.handle,
        "follower_count": _first_present(profile, "follower_count", "mplatform_followers_count", "fans_count"),
        "following_count": _first_present(profile, "following_count", "following"),
    }
    page_text = (html or "").lower()
    title = (page_title or "").lower()
    resolved_page_url = page_url or profile_url
    browser_surface_status = None
    browser_surface_reason = None
    if _looks_like_challenge_surface(title, page_text, resolved_page_url):
        browser_surface_status = "blocked"
        browser_surface_reason = "browser_profile_detected_challenge_page"
    elif _looks_like_login_surface(title, page_text, resolved_page_url):
        browser_surface_status = "login_required"
        browser_surface_reason = "browser_profile_detected_login_required"

    response_shape = "browser_rendered_shell"
    if network_documents and videos:
        response_shape = "browser_network_payload"
    elif html_documents and videos:
        response_shape = "browser_rendered_payload"
    elif videos:
        response_shape = "browser_rendered_links"
    elif documents:
        response_shape = "browser_rendered_zero_payload"

    return {
        "profile": {key: value for key, value in normalized_profile.items() if value is not None},
        "videos": videos,
        "metadata": {
            "source": "douyin_browser_profile",
            "embedded_document_count": len(html_documents),
            "browser_response_document_count": len(network_documents),
            "extracted_at": datetime.now(UTC).isoformat(),
            "response_shape": response_shape,
            "profile_payload_present": bool(profile),
            "video_candidate_count": len(videos),
            "browser_video_link_count": len(video_links or []),
            "browser_page_title": page_title,
            "browser_page_url": page_url,
            "browser_surface_status": browser_surface_status,
            "browser_surface_reason": browser_surface_reason,
            "parse_strategy": parser_strategy,
        },
    }


def _embedded_json_documents(html: str) -> Iterator[dict | list]:
    script_pattern = re.compile(r"<script[^>]*(?:id=[\"'](?:RENDER_DATA|SIGI_STATE|__UNIVERSAL_DATA_FOR_REHYDRATION__)[\"'][^>]*)?[^>]*>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE)
    for match in script_pattern.finditer(html):
        body = match.group("body").strip()
        parsed = _parse_jsonish(body)
        if parsed is not None:
            yield parsed

    for marker in ("window.__INIT_PROPS__", "window.__INITIAL_STATE__", "window.__UNIVERSAL_DATA_FOR_REHYDRATION__", "__UNIVERSAL_DATA_FOR_REHYDRATION__"):
        for parsed in _parse_json_after_marker(html, marker):
            yield parsed


def _parse_jsonish(value: str) -> dict | list | None:
    if not value:
        return None
    candidates = [value, unescape(value), unquote(unescape(value))]
    for candidate in candidates:
        stripped = candidate.strip().rstrip(";")
        if not stripped or stripped[0] not in "[{":
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict | list):
            return parsed
    return None


def _parse_json_after_marker(html: str, marker: str) -> Iterator[dict | list]:
    decoder = json.JSONDecoder()
    start = 0
    while True:
        marker_index = html.find(marker, start)
        if marker_index == -1:
            break
        equals_index = html.find("=", marker_index)
        if equals_index == -1:
            break
        json_start = equals_index + 1
        while json_start < len(html) and html[json_start].isspace():
            json_start += 1
        try:
            parsed, end = decoder.raw_decode(html[json_start:])
        except json.JSONDecodeError:
            start = marker_index + len(marker)
            continue
        if isinstance(parsed, dict | list):
            yield parsed
        start = json_start + end


def _find_profile(documents: list[dict | list]) -> dict | None:
    best: dict | None = None
    best_score = 0
    for item in _walk_json(documents):
        if not isinstance(item, dict):
            continue
        score = 0
        if any(key in item for key in ("sec_uid", "uid", "user_id")):
            score += 3
        if any(key in item for key in ("nickname", "display_name", "unique_id")):
            score += 3
        if any(key in item for key in ("follower_count", "mplatform_followers_count", "following_count")):
            score += 1
        if score > best_score:
            best = item
            best_score = score
    return best if best_score >= 3 else None


def _find_videos(documents: list[dict | list], *, max_videos: int) -> list[dict]:
    videos: list[dict] = []
    seen: set[str] = set()
    for item in _walk_json(documents):
        if not isinstance(item, dict) or not _looks_like_video(item):
            continue
        external_id = str(item.get("aweme_id") or item.get("video_id") or item.get("id"))
        if external_id in seen:
            continue
        seen.add(external_id)
        videos.append(item)
        if len(videos) >= max_videos:
            break
    return videos


def _looks_like_video(item: dict) -> bool:
    if not (item.get("aweme_id") or item.get("video_id") or item.get("id")):
        return False
    return any(key in item for key in ("statistics", "stats", "desc", "create_time", "duration", "video"))


def _walk_json(value: object) -> Iterator[object]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _first_present(container: dict, *keys: str) -> object:
    for key in keys:
        value = container.get(key)
        if value is not None:
            return value
    return None


def _videos_from_rendered_links(links: list[str], *, max_videos: int) -> list[dict]:
    videos: list[dict] = []
    seen: set[str] = set()
    for link in links:
        if not isinstance(link, str) or not link.strip():
            continue
        absolute = urljoin("https://www.douyin.com", link.strip())
        parsed = urlparse(absolute)
        match = re.search(r"/video/([^/?#]+)", parsed.path)
        if not match:
            continue
        external_id = match.group(1)
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        videos.append(
            {
                "aweme_id": external_id,
                "id": external_id,
                "share_url": absolute,
                "source_video_url": absolute,
                "statistics": {},
                "desc": None,
            }
        )
        if len(videos) >= max_videos:
            break
    return videos


def classify_zero_video_payload(
    payload: dict,
    *,
    probe: DouyinRenderedPageProbe | None = None,
) -> dict | None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if payload.get("videos"):
        return None
    if probe is not None:
        if probe.status == "blocked":
            return {
                "result": "blocked",
                "code": "blocked_response",
                "message": "Douyin rendered a challenge or blocked page before profile videos could load.",
                "blocked_reason": "challenge_required",
                "metrics": {
                    "embedded_document_count": metadata.get("embedded_document_count", 0),
                    "video_link_count": probe.video_link_count,
                },
            }
        if probe.status == "login_required":
            return {
                "result": "blocked",
                "code": "login_required",
                "message": "Douyin redirected the connected account back to login before profile videos could load.",
                "blocked_reason": "login_required",
                "metrics": {
                    "embedded_document_count": metadata.get("embedded_document_count", 0),
                    "video_link_count": probe.video_link_count,
                },
            }
        if probe.status == "rendered_videos_present":
            return {
                "result": "failed",
                "code": "parse_failed",
                "message": "Douyin rendered profile videos in-browser, but the canonical HTML parser did not expose a usable video payload.",
                "blocked_reason": "unsupported_shape",
                "metrics": {
                    "embedded_document_count": metadata.get("embedded_document_count", 0),
                    "video_link_count": probe.video_link_count,
                },
            }
    browser_surface_status = metadata.get("browser_surface_status")
    if browser_surface_status == "blocked":
        return {
            "result": "blocked",
            "code": "blocked_response",
            "message": "Douyin rendered a challenge or blocked page in the reusable browser profile before profile videos could load.",
            "blocked_reason": metadata.get("browser_surface_reason") or "challenge_required",
            "metrics": {
                "embedded_document_count": metadata.get("embedded_document_count", 0),
                "browser_response_document_count": metadata.get("browser_response_document_count", 0),
                "video_link_count": metadata.get("browser_video_link_count", 0),
            },
        }
    if browser_surface_status == "login_required":
        return {
            "result": "blocked",
            "code": "login_required",
            "message": "The reusable browser profile was redirected back to login before profile videos could load.",
            "blocked_reason": metadata.get("browser_surface_reason") or "login_required",
            "metrics": {
                "embedded_document_count": metadata.get("embedded_document_count", 0),
                "browser_response_document_count": metadata.get("browser_response_document_count", 0),
                "video_link_count": metadata.get("browser_video_link_count", 0),
            },
        }
    if metadata.get("response_shape") == "html_shell":
        return {
            "result": "failed",
            "code": "parse_zero_videos",
            "message": "Douyin returned an HTML shell without parseable embedded profile videos.",
            "blocked_reason": "unsupported_shape",
            "metrics": {
                "embedded_document_count": metadata.get("embedded_document_count", 0),
                "video_candidate_count": metadata.get("video_candidate_count", 0),
            },
        }
    if metadata.get("response_shape") in {"browser_rendered_shell", "browser_rendered_zero_payload"}:
        return {
            "result": "failed",
            "code": "parse_zero_videos",
            "message": "Douyin browser-profile fetch completed, but the rendered profile did not expose parseable videos.",
            "blocked_reason": "browser_profile_zero_videos",
            "metrics": {
                "embedded_document_count": metadata.get("embedded_document_count", 0),
                "browser_response_document_count": metadata.get("browser_response_document_count", 0),
                "video_link_count": metadata.get("browser_video_link_count", 0),
            },
        }
    return {
        "result": "warning",
        "code": "true_zero_videos",
        "message": "Douyin returned a parseable profile payload with zero videos.",
        "blocked_reason": None,
        "metrics": {
            "embedded_document_count": metadata.get("embedded_document_count", 0),
            "video_candidate_count": metadata.get("video_candidate_count", 0),
        },
    }


def _cookies_from_cookie_header(cookie_header: str | None) -> list[dict]:
    if not cookie_header:
        return []
    cookies: list[dict] = []
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or not value:
            continue
        cookies.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})
    return cookies


def _looks_like_challenge_surface(title: str, body_text: str, page_url: str) -> bool:
    markers = (
        "captcha",
        "security check",
        "verify that you",
        "verify you are human",
        "\u9a8c\u8bc1\u7801",
        "\u5b89\u5168\u9a8c\u8bc1",
    )
    return any(marker in title or marker in body_text or marker in page_url.lower() for marker in markers)


def _looks_like_login_surface(title: str, body_text: str, page_url: str) -> bool:
    markers = (
        "login",
        "passport",
        "\u767b\u5f55",
        "\u8bf7\u5148\u767b\u5f55",
    )
    return any(marker in title or marker in body_text or marker in page_url.lower() for marker in markers)
