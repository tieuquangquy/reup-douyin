// @ts-nocheck
(() => {
  const MAX_CACHE_ITEMS = 240;
  const MAX_PROBE_TARGETS = 80;
  const MAX_PROBE_DESC = 280;
  const MAX_PROBE_TEXT_SIZE = 1_500_000;
  const CACHE_ELEMENT_ID = "reup-douyin-network-cache";
  const CACHE_EVENT_TYPE = "REUP_DOUYIN_NETWORK_CACHE_UPDATE";
  const PROBE_READY_EVENT_TYPE = "REUP_DOUYIN_NETWORK_PROBE_READY_22C12A_R3";
  const PROBE_EVENT_TYPE = "REUP_DOUYIN_NETWORK_AWEME_BATCH_22C12A_R3";
  const win = window;
  if (win.__REUP_DOUYIN_NETWORK_HOOK_INSTALLED__) {
    publishPassiveProbeReady22C12A();
    return;
  }
  win.__REUP_DOUYIN_NETWORK_HOOK_INSTALLED__ = true;
  win.__REUP_DOUYIN_NETWORK_CACHE__ = win.__REUP_DOUYIN_NETWORK_CACHE__ || [];
  win.__DOUYIN_AWEME_CACHE__ = win.__DOUYIN_AWEME_CACHE__ || {};
  publishPassiveProbeReady22C12A();

  const originalFetch = win.fetch.bind(win);
  win.fetch = async (...args) => {
    const response = await originalFetch(...args);
    console.log("[NETWORK_HIT]", response.url);
    observeResponse(response.url || String(args[0] || "fetch"), response.clone(), methodFromFetchArgs(args), response.status || null);
    return response;
  };

  const OriginalXHR = win.XMLHttpRequest;
  const originalOpen = OriginalXHR.prototype.open;
  const originalSend = OriginalXHR.prototype.send;
  OriginalXHR.prototype.open = function open(method, url, async = true, username, password) {
    this.__reupDouyinUrl = String(url);
    this.__reupDouyinMethod = String(method || "GET").toUpperCase();
    return originalOpen.call(this, method, url, async, username, password);
  };
  OriginalXHR.prototype.send = function send(body) {
    this.addEventListener("load", () => {
      const responseUrl = this.responseURL || this.__reupDouyinUrl || "xhr";
      console.log("[NETWORK_HIT]", responseUrl);
      const text = safeXhrResponseText(this);
      if (typeof text !== "string") return;
      if (text.length > MAX_PROBE_TEXT_SIZE) return;
      observeJson(responseUrl, safeParseJson(text), this.__reupDouyinMethod || "GET", typeof this.status === "number" ? this.status : null);
    });
    return originalSend.call(this, body);
  };

  function safeXhrResponseText(xhr) {
    const responseType = xhr.responseType || "";
    if (responseType !== "" && responseType !== "text") return null;
    try {
      return typeof xhr.responseText === "string" ? xhr.responseText : null;
    } catch {
      return null;
    }
  }

  function observeResponse(url, response, method, status) {
    response.text().then((text) => {
      if (typeof text !== "string" || text.length > MAX_PROBE_TEXT_SIZE) return;
      observeJson(url, safeParseJson(text), method, status);
    }).catch(() => undefined);
  }

  function observeJson(source, json, method = "GET", status = null) {
    if (!json) return;
    const observedAt = new Date().toISOString();
    const context = currentCaptureContext(observedAt);
    const normalized = normalizeDouyinNetworkPayload(json, safeSource(source)).map((item) => ({
      ...item,
      observed_at: observedAt,
      context
    }));
    if (!normalized.length) return;
    for (const item of normalized) {
      if (item.aweme_id) {
        cacheAwemeMetadata({
          aweme_id: item.aweme_id,
          create_time: item.posted_at ? Date.parse(item.posted_at) / 1000 : null,
          video: item.duration_seconds != null ? { duration: item.duration_seconds * 1000 } : null,
          statistics: {
            play_count: item.view_count,
            digg_count: item.like_count,
            comment_count: item.comment_count,
            share_count: item.share_count
          }
        });
      }
    }
    const current = win.__REUP_DOUYIN_NETWORK_CACHE__ || [];
    win.__REUP_DOUYIN_NETWORK_CACHE__ = mergeItems([...normalized, ...current]).slice(0, MAX_CACHE_ITEMS);
    publishCache(win.__REUP_DOUYIN_NETWORK_CACHE__);
    const probeBatch = extractPassiveProbeBatch22C12A(json, source, method, status);
    if (probeBatch) publishPassiveProbeBatch22C12A(probeBatch);
  }

  function cacheAwemeMetadata(item) {
    const awemeId = String(item.aweme_id).trim();
    if (!awemeId) return;
    const statistics = objectValue(item.statistics);
    const video = objectValue(item.video);
    const cachedData = {
      posted_at: postedAtFromCreateTime(item.create_time),
      duration_seconds: durationSecondsFromVideo(video),
      view_count: countValue(statistics && statistics.play_count),
      like_count: countValue(statistics && statistics.digg_count),
      comment_count: countValue(statistics && statistics.comment_count),
      share_count: countValue(statistics && statistics.share_count)
    };
    win.__DOUYIN_AWEME_CACHE__ = win.__DOUYIN_AWEME_CACHE__ || {};
    win.__DOUYIN_AWEME_CACHE__[awemeId] = cachedData;
    console.log("[AWEME_CACHED]", awemeId, cachedData);
  }

  function postedAtFromCreateTime(value) {
    return validPostedAtFromEpochSeconds(numberValue(value));
  }

  function durationSecondsFromVideo(video) {
    const durationMilliseconds = numberValue(video && video.duration);
    if (typeof durationMilliseconds !== "number" || !Number.isFinite(durationMilliseconds) || durationMilliseconds < 0) return null;
    const seconds = durationMilliseconds / 1000;
    return Number.isFinite(seconds) ? seconds : null;
  }

  function normalizeDouyinNetworkPayload(payload, source = "network_json") {
    const items = [];
    visit(payload, source, items, new WeakSet(), 0);
    return mergeItems(items).slice(0, MAX_CACHE_ITEMS);
  }

  function visit(value, source, items, seenObjects, depth) {
    if (!value || depth > 12) return;
    if (typeof value === "string") {
      const nested = safeParseJson(value);
      if (nested) visit(nested, source, items, seenObjects, depth + 1);
      return;
    }
    if (typeof value !== "object" || seenObjects.has(value)) return;
    seenObjects.add(value);
    const item = normalizeAwemeRecord(value, source);
    if (item) items.push(item);
    for (const child of Object.values(value)) {
      if (Array.isArray(child)) child.forEach((entry) => visit(entry, source, items, seenObjects, depth + 1));
      else visit(child, source, items, seenObjects, depth + 1);
    }
  }

  function normalizeAwemeRecord(record, source) {
    const awemeId = stringValue(record.aweme_id);
    if (!awemeId || !looksLikeAwemeRecord(record)) return null;
    const video = objectValue(record.video) || objectValue(record.video_info) || objectValue(record.videoInfo);
    const statistics = objectValue(record.statistics) || objectValue(record.stats) || objectValue(record.statistics_info) || objectValue(record.statisticsInfo);
    const shareInfo = objectValue(record.share_info) || objectValue(record.shareInfo);
    const covers = collectCoverCandidates(record, video);
    const createTime = numberValue(record.create_time) || numberValue(record.createTime) || numberValue(record.create_time_ms);
    const durationRaw = numberValue(video && video.duration) || numberValue(video && video.duration_ms) || numberValue(record.duration) || numberValue(record.duration_ms);
    const durationSeconds = normalizeDurationSeconds(durationRaw);
    const durationText = validDurationText(stringValue(record.duration_text) || stringValue(record.durationText));
    const postedAt = validPostedAtFromEpochSeconds(createTime);
    const viewMetric = metricValue(statistics, ["play_count", "view_count", "playCount"]);
    const likeMetric = metricValue(statistics, ["digg_count", "like_count", "diggCount"]);
    const commentMetric = metricValue(statistics, ["comment_count", "commentCount"]);
    const shareMetric = metricValue(statistics, ["share_count", "shareCount"]);
    const engagementRate = deriveEngagementRate({
      view_count: viewMetric.value,
      like_count: likeMetric.value,
      comment_count: commentMetric.value,
      share_count: shareMetric.value
    });
    const rawAweme = boundedRawEvidence(record);
    const rawEvidenceField = isDetailEvidenceSource(source) ? { raw_detail_aweme: rawAweme } : { raw_network_aweme: rawAweme };
    return {
      aweme_id: awemeId,
      title: stringValue(record.title) || stringValue(record.desc),
      desc: stringValue(record.desc) || stringValue(record.title),
      share_url: stringValue(record.share_url) || stringValue(shareInfo && shareInfo.share_url) || stringValue(record.url),
      thumbnail_url: covers[0] || null,
      cover_url: firstCover(video && video.cover) || covers[0] || null,
      origin_cover: firstCover(video && video.origin_cover),
      dynamic_cover: firstCover(video && video.dynamic_cover),
      url_list: covers,
      poster_aspect_ratio: 9 / 16,
      duration_text: durationText,
      duration_seconds: durationSeconds,
      posted_at: postedAt,
      view_count: viewMetric.value,
      view_count_text: viewMetric.raw,
      like_count: likeMetric.value,
      like_count_text: likeMetric.raw,
      comment_count: commentMetric.value,
      comment_count_text: commentMetric.raw,
      share_count: shareMetric.value,
      engagement_rate: engagementRate,
      raw_source: source,
      ...rawEvidenceField
    };
  }

  function isDetailEvidenceSource(source) {
    return /detail|hydrate|share/i.test(source);
  }

  function boundedRawEvidence(value, depth = 0) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const output = {};
    for (const [key, child] of Object.entries(value).slice(0, 80)) {
      if (isSecretLikeKey(key)) continue;
      output[key] = boundedRawValue(child, depth + 1);
    }
    return output;
  }

  function boundedRawValue(value, depth) {
    if (value === null || typeof value === "number" || typeof value === "boolean") return value;
    if (typeof value === "string") return value.length > 600 ? `${value.slice(0, 600)}…` : value;
    if (!value || typeof value !== "object") return null;
    if (depth >= 5) return "[Truncated]";
    if (Array.isArray(value)) return value.slice(0, 12).map((entry) => boundedRawValue(entry, depth + 1));
    const output = {};
    for (const [key, child] of Object.entries(value).slice(0, 80)) {
      if (isSecretLikeKey(key)) continue;
      output[key] = boundedRawValue(child, depth + 1);
    }
    return output;
  }

  function isSecretLikeKey(key) {
    return /cookie|authorization|auth|token|secret|credential|password|passwd|session|header|csrf/i.test(key);
  }

  function publishCache(items) {
    let element = document.getElementById(CACHE_ELEMENT_ID);
    if (!element) {
      element = document.createElement("script");
      element.id = CACHE_ELEMENT_ID;
      element.type = "application/json";
      document.documentElement.appendChild(element);
    }
    element.textContent = JSON.stringify(items.slice(0, MAX_CACHE_ITEMS));
    win.postMessage({ type: CACHE_EVENT_TYPE, items: items.slice(0, MAX_CACHE_ITEMS) }, win.location.origin);
  }

  function publishPassiveProbeBatch22C12A(batch) {
    win.postMessage({ type: PROBE_EVENT_TYPE, traceVersion: "22C-12A-R3", ...batch }, win.location.origin);
  }

  function publishPassiveProbeReady22C12A() {
    win.postMessage({ type: PROBE_READY_EVENT_TYPE, traceVersion: "22C-12A-R3" }, win.location.origin);
  }

  function extractPassiveProbeBatch22C12A(payload, source, method, status) {
    const requestUrl = safeRequestUrl22C13B(source);
    const targets = collectPassiveProbeTargets22C12A(payload).slice(0, MAX_PROBE_TARGETS).map((target) => ({
      ...target,
      request_url: requestUrl
    }));
    if (!targets.length) return null;
    const cursorFields = extractCursorFields22C12BR2(payload);
    return {
      urlPath: sanitizeUrlPath22C12A(source),
      requestUrl,
      method: String(method || "GET").toUpperCase(),
      status: typeof status === "number" ? status : null,
      detectedShape: detectProbeShape22C12A(payload),
      hasMore: cursorFields.has_more ?? cursorFields.hasMore,
      cursor: cursorFields.cursor ?? cursorFields.max_cursor ?? cursorFields.next_cursor,
      cursorFields,
      awemeCount: targets.length,
      targets
    };
  }

  function collectPassiveProbeTargets22C12A(payload) {
    const targets = new Map();
    visitPassiveProbe22C12A(payload, new WeakSet(), (record) => {
      const target = normalizePassiveProbeTarget22C12A(record);
      if (!target || targets.has(target.aweme_id)) return;
      targets.set(target.aweme_id, target);
    });
    return Array.from(targets.values());
  }

  function visitPassiveProbe22C12A(value, seen, onRecord, depth = 0) {
    if (!value || typeof value !== "object" || depth > 10) return;
    if (seen.has(value)) return;
    seen.add(value);
    if (Array.isArray(value)) {
      value.forEach((entry) => visitPassiveProbe22C12A(entry, seen, onRecord, depth + 1));
      return;
    }
    onRecord(value);
    Object.values(value).forEach((child) => visitPassiveProbe22C12A(child, seen, onRecord, depth + 1));
  }

  function normalizePassiveProbeTarget22C12A(record) {
    const awemeId = stringValue(record.aweme_id) || stringValue(record.awemeId) || stringValue(record.aweme_id_str) || stringValue(record.awemeIdStr);
    if (!awemeId || !/^\d{6,22}$/.test(awemeId)) return null;
    const video = objectValue(record.video) || objectValue(record.video_info) || objectValue(record.videoInfo);
    const statistics = objectValue(record.statistics) || objectValue(record.stats);
    return {
      aweme_id: awemeId,
      source_url: `https://www.douyin.com/video/${awemeId}`,
      desc: truncateProbeDesc22C12A(stringValue(record.desc) || stringValue(record.caption) || stringValue(record.title)),
      cover_url: firstCover(video && video.cover) || firstCover(video && video.origin_cover) || firstCover(record.cover) || firstCover(record.origin_cover),
      duration: normalizeProbeDuration22C12A(numberValue(video && video.duration) || numberValue(record.duration)),
      create_time: numberValue(record.create_time) || numberValue(record.createTime) || null,
      like_count: metricValue22C12A(statistics, record, ["digg_count", "like_count", "diggCount", "likeCount"]),
      comment_count: metricValue22C12A(statistics, record, ["comment_count", "commentCount"]),
      share_count: metricValue22C12A(statistics, record, ["share_count", "shareCount"])
    };
  }

  function metricValue22C12A(statistics, record, keys) {
    for (const key of keys) {
      const fromStats = numberValue(statistics && statistics[key]);
      if (typeof fromStats === "number") return fromStats;
      const fromRecord = numberValue(record[key]);
      if (typeof fromRecord === "number") return fromRecord;
    }
    return null;
  }

  function detectProbeShape22C12A(payload) {
    const shapes = [
      { path: ["aweme_list"], label: "aweme_list" },
      { path: ["awemeList"], label: "awemeList" },
      { path: ["item_list"], label: "item_list" },
      { path: ["items"], label: "items" },
      { path: ["data", "list"], label: "data.list" },
      { path: ["data", "aweme_list"], label: "data.aweme_list" }
    ];
    for (const shape of shapes) {
      const value = readPath22C12A(payload, shape.path);
      if (Array.isArray(value) && value.length > 0) return shape.label;
    }
    return "recursive_aweme_record";
  }

  function readPath22C12A(value, ...paths) {
    for (const path of paths) {
      let current = value;
      let matched = true;
      for (const key of path) {
        if (!current || typeof current !== "object" || !(key in current)) {
          matched = false;
          break;
        }
        current = current[key];
      }
      if (matched) return current;
    }
    return undefined;
  }

  function sanitizeUrlPath22C12A(value) {
    try {
      const parsed = new URL(String(value || ""), win.location.href);
      return parsed.pathname || "/";
    } catch {
      return String(value || "").split("?")[0] || "/";
    }
  }

  function safeRequestUrl22C13B(value) {
    try {
      const parsed = new URL(String(value || ""), win.location.href);
      parsed.hash = "";
      if (parsed.origin !== win.location.origin) return null;
      return parsed.toString();
    } catch {
      return null;
    }
  }

  function methodFromFetchArgs(args) {
    const input = args[0];
    const init = args[1];
    if (init && typeof init === "object" && typeof init.method === "string") return init.method;
    if (input && typeof input === "object" && typeof input.method === "string") return input.method;
    return "GET";
  }

  function booleanOrNull22C12A(value) {
    if (typeof value === "boolean") return value;
    if (value === 1 || value === "1" || value === "true" || value === "yes") return true;
    if (value === 0 || value === "0" || value === "false" || value === "no") return false;
    return null;
  }

  function extractCursorFields22C12BR2(payload) {
    return {
      cursor: cursorValue22C12A(readPath22C12A(payload, ["cursor"], ["data", "cursor"])),
      max_cursor: cursorValue22C12A(readPath22C12A(payload, ["max_cursor"], ["data", "max_cursor"])),
      min_cursor: cursorValue22C12A(readPath22C12A(payload, ["min_cursor"], ["data", "min_cursor"])),
      next_cursor: cursorValue22C12A(readPath22C12A(payload, ["next_cursor"], ["data", "next_cursor"])),
      has_more: booleanOrNull22C12A(readPath22C12A(payload, ["has_more"], ["data", "has_more"])),
      hasMore: booleanOrNull22C12A(readPath22C12A(payload, ["hasMore"], ["data", "hasMore"])),
      offset: cursorValue22C12A(readPath22C12A(payload, ["offset"], ["data", "offset"])),
      page: cursorValue22C12A(readPath22C12A(payload, ["page"], ["data", "page"])),
      next: cursorValue22C12A(readPath22C12A(payload, ["next"], ["data", "next"]))
    };
  }

  function cursorValue22C12A(value) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim()) return value.trim();
    return null;
  }

  function truncateProbeDesc22C12A(value) {
    if (!value) return null;
    return value.length > MAX_PROBE_DESC ? `${value.slice(0, MAX_PROBE_DESC)}...` : value;
  }

  function normalizeProbeDuration22C12A(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
    return value > 1000 ? Math.round(value / 1000) : Math.round(value);
  }

  function looksLikeAwemeRecord(record) {
    return Boolean(record.aweme_id && (record.video || record.video_info || record.videoInfo || record.statistics || record.stats || record.statistics_info || record.statisticsInfo || record.share_info || record.desc || record.create_time));
  }

  function collectCoverCandidates(record, video) {
    return uniqueStrings([
      ...coverList(video && video.origin_cover),
      ...coverList(video && video.cover),
      ...coverList(video && video.dynamic_cover),
      ...coverList(video && video.poster),
      ...coverList(video && video.poster_url),
      ...coverList(video && video.thumbnail),
      ...coverList(video && video.thumbnail_url),
      ...coverList(video && video.thumb_url),
      ...coverList(video && video.image),
      ...coverList(video && video.image_url),
      ...coverList(video && video.animated_cover),
      ...coverList(record.origin_cover),
      ...coverList(record.cover),
      ...coverList(record.dynamic_cover),
      ...coverList(record.poster),
      ...coverList(record.poster_url),
      ...coverList(record.thumbnail),
      ...coverList(record.thumbnail_url),
      ...coverList(record.thumb_url),
      ...coverList(record.image),
      ...coverList(record.image_url),
      ...coverList(record.animated_cover)
    ].map(normalizeUrl).filter(Boolean));
  }

  function firstCover(value) {
    return coverList(value).map(normalizeUrl).find(Boolean) || null;
  }

  function coverList(value) {
    if (!value) return [];
    if (typeof value === "string") return [value];
    if (Array.isArray(value)) return value.filter((entry) => typeof entry === "string");
    if (typeof value !== "object") return [];
    return [
      stringValue(value.url),
      stringValue(value.uri),
      stringValue(value.src),
      stringValue(value.href),
      stringValue(value.poster),
      stringValue(value.poster_url),
      stringValue(value.thumbnail_url),
      stringValue(value.thumb_url),
      stringValue(value.image_url),
      ...coverList(value.url_list),
      ...coverList(value.urlList),
      ...coverList(value.urls)
    ].filter(Boolean);
  }

  function currentCaptureContext(observedAt) {
    const pageUrl = win.location.href;
    const profileUrl = profileUrlFromPage(pageUrl);
    const profileExternalId = profileExternalIdFromUrl(profileUrl);
    const pageUrlNormalized = normalizeContextUrl(pageUrl);
    return {
      page_url: pageUrl,
      page_url_normalized: pageUrlNormalized,
      profile_url: profileUrl,
      profile_external_id: profileExternalId,
      captured_at: observedAt,
      cache_scope_key: [pageUrlNormalized, profileUrl, profileExternalId].filter(Boolean).join("|") || null
    };
  }

  function normalizeContextUrl(value) {
    if (!value) return null;
    try {
      const parsed = new URL(value, "https://www.douyin.com");
      return `${parsed.origin}${parsed.pathname.replace(/\/+$/, "")}`;
    } catch {
      return null;
    }
  }

  function profileUrlFromPage(url) {
    if (!url) return null;
    try {
      const parsed = new URL(url);
      const userMatch = /\/user\/([^/?#]+)/.exec(parsed.pathname);
      if (userMatch && userMatch[1]) return `https://www.douyin.com/user/${userMatch[1]}`;
      const path = parsed.pathname.replace(/^\//, "");
      if (path.startsWith("@")) return `https://www.douyin.com/${path.split("/")[0]}`;
    } catch {
      return null;
    }
    return null;
  }

  function profileExternalIdFromUrl(url) {
    if (!url) return null;
    try {
      const parsed = new URL(url);
      const userMatch = /\/user\/([^/?#]+)/.exec(parsed.pathname);
      return (userMatch && userMatch[1]) || null;
    } catch {
      return null;
    }
  }

  function mergeItems(items) {
    const byId = new Map();
    for (const item of items) {
      const awemeId = item.aweme_id && String(item.aweme_id).trim();
      if (!awemeId) continue;
      const previous = byId.get(awemeId);
      byId.set(awemeId, {
        ...previous,
        ...item,
        aweme_id: awemeId,
        url_list: uniqueStrings([...(item.url_list || []), ...((previous && previous.url_list) || [])]),
        context: item.context || (previous && previous.context) || null,
        raw_network_aweme: item.raw_network_aweme || (previous && previous.raw_network_aweme) || null,
        raw_detail_aweme: item.raw_detail_aweme || (previous && previous.raw_detail_aweme) || null
      });
    }
    return Array.from(byId.values()).map((item) => ({ ...item, url_list: [...(item.url_list || [])] }));
  }

  function normalizeUrl(value) {
    const trimmed = value && value.trim();
    if (!trimmed) return null;
    try {
      return new URL(trimmed, "https://www.douyin.com").href;
    } catch {
      return null;
    }
  }

  function isDouyinUrl(value) {
    try {
      const host = new URL(value, win.location.href).hostname.toLowerCase();
      return host.includes("douyin.com") || host.includes("iesdouyin.com") || host.includes("byteimg.com") || host.includes("douyinpic.com");
    } catch {
      return false;
    }
  }

  function safeSource(value) {
    try {
      const url = new URL(value, win.location.href);
      return `${url.hostname}${url.pathname}`.slice(0, 180);
    } catch {
      return "network_json";
    }
  }

  function safeParseJson(value) {
    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    if (!trimmed || (trimmed[0] !== "{" && trimmed[0] !== "[")) return null;
    try {
      return JSON.parse(trimmed);
    } catch {
      return null;
    }
  }

  function objectValue(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  }

  function metricValue(record, keys) {
    for (const key of keys) {
      const rawValue = record && record[key];
      const value = countValue(rawValue);
      const raw = typeof rawValue === "string" && rawValue.trim() ? rawValue.trim() : null;
      if (typeof value === "number" || raw) return { value, raw };
    }
    return { value: null, raw: null };
  }

  function stringValue(value) {
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value).trim();
    return null;
  }

  function numberValue(value) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim()) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  }

  function countValue(value) {
    const numeric = numberValue(value);
    if (typeof numeric !== "number" || !Number.isFinite(numeric)) return null;
    if (numeric < 0) return null;
    return Math.round(numeric);
  }

  function deriveEngagementRate(values) {
    const views = values.view_count;
    if (typeof views !== "number" || !Number.isFinite(views) || views <= 0) return null;
    const likes = typeof values.like_count === "number" ? values.like_count : 0;
    const comments = typeof values.comment_count === "number" ? values.comment_count : 0;
    const shares = typeof values.share_count === "number" ? values.share_count : 0;
    const numerator = likes + comments + shares;
    if (!Number.isFinite(numerator) || numerator < 0) return null;
    const rate = numerator / views;
    return Number.isFinite(rate) && rate >= 0 ? rate : null;
  }

  function uniqueStrings(values) {
    const seen = new Set();
    const unique = [];
    for (const value of values) {
      if (!value || seen.has(value)) continue;
      seen.add(value);
      unique.push(value);
    }
    return unique;
  }

  function normalizeDurationSeconds(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
    const seconds = value > 1000 ? value / 1000 : value;
    if (!Number.isFinite(seconds) || seconds < 0 || seconds > 86400) return null;
    return Math.round(seconds);
  }

  function validDurationText(value) {
    if (!value) return null;
    const trimmed = String(value).trim();
    return /^(?:\d{1,2}:)?\d{1,2}:\d{2}$/.test(trimmed) ? trimmed : null;
  }

  function validPostedAtFromEpochSeconds(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return null;
    const epochMilliseconds = value > 100000000000 ? value : value * 1000;
    const parsed = new Date(epochMilliseconds);
    if (Number.isNaN(parsed.getTime())) return null;
    if (parsed.getUTCHours() === 0 && parsed.getUTCMinutes() === 0 && parsed.getUTCSeconds() === 0 && parsed.getUTCMilliseconds() === 0) return null;
    return parsed.toISOString();
  }
})();
