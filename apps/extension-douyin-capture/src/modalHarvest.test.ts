import assert from "node:assert/strict";
import { parseCompactCountFromOcr, readCalibratedPointMetrics } from "./calibratedPoint";
import {
  FullModalHarvestController,
  PRODUCTION_EVIDENCE_COLLECTION_VERSION,
  auditHarvestRecentItemsIntegrity,
  buildDomDetailEvidenceSummary,
  clickCalibratedNextPoint,
  detectCurrentAwemeId,
  extractCurrentModalMetricsForAweme,
  navigateDirectlyToTargetModal,
  navigateNextModalAutomatically,
  navigateNextVideoByCalibratedPoint,
  probeCurrentModalMetrics,
  waitForCurrentModalMetrics,
  waitForModalIdChange
} from "./modalHarvest";
import type { CaptureContext, RightRailCalibration, StoredFullModalHarvestState } from "./types";

type Rect = { x: number; y: number; width: number; height: number };

class FakeElement {
  tagName: string;
  innerText: string;
  textContent: string;
  className = "";
  style: Record<string, string> = {};
  parentElement: FakeElement | null = null;
  children: FakeElement[] = [];
  dispatchedEvents: string[] = [];
  private attrs = new Map<string, string>();

  constructor(tagName: string, text: string, private rect: Rect) {
    this.tagName = tagName.toUpperCase();
    this.innerText = text;
    this.textContent = text;
  }

  getBoundingClientRect(): Rect {
    return this.rect;
  }

  getAttribute(name: string): string | null {
    return this.attrs.get(name) ?? null;
  }

  setAttribute(name: string, value: string): void {
    this.attrs.set(name, value);
  }

  appendChild(child: FakeElement): void {
    child.parentElement = this;
    this.children.push(child);
  }

  dispatchEvent(event: { type: string; key?: string }): boolean {
    this.dispatchedEvents.push(event.key ? `${event.type}:${event.key}` : event.type);
    return true;
  }

  click(): void {
    this.dispatchedEvents.push("click");
  }

  focus(): void {
    this.dispatchedEvents.push("focus");
  }
}

class FakeVideoElement extends FakeElement {
  paused: boolean;
  duration: number;
  currentTime = 0;
  constructor(duration: number, paused: boolean, rect: Rect) {
    super("video", "", rect);
    this.duration = duration;
    this.paused = paused;
  }
}

type FakeDocumentOptions = {
  href: string;
  viewportWidth?: number;
  viewportHeight?: number;
  bodyText?: string;
  elementsFromPoint?: (x: number, y: number) => FakeElement[];
  elementFromPoint?: (x: number, y: number) => FakeElement | null;
  videos?: FakeVideoElement[];
  anchors?: FakeElement[];
};

function createFakeDocument(options: FakeDocumentOptions): Document {
  const viewportWidth = options.viewportWidth ?? 1000;
  const viewportHeight = options.viewportHeight ?? 900;
  const videos = options.videos ?? [];
  const anchors = options.anchors ?? [];
  const body = new FakeElement("body", options.bodyText ?? "", { x: 0, y: 0, width: viewportWidth, height: viewportHeight });
  const documentElement = new FakeElement("html", "", { x: 0, y: 0, width: viewportWidth, height: viewportHeight }) as FakeElement & {
    clientWidth: number;
    clientHeight: number;
  };
  documentElement.clientWidth = viewportWidth;
  documentElement.clientHeight = viewportHeight;

  const document = {
    title: "",
    body,
    documentElement,
    dispatchedEvents: [] as string[],
    querySelectorAll(selector: string) {
      if (selector === "video") return videos;
      if (selector === 'a[href*="/video/"]') return anchors;
      return [];
    },
    querySelector(selector: string) {
      if (selector.includes('a[href*="/video/"]')) return anchors[0] ?? null;
      if (selector.includes("next")) return options.elementFromPoint?.(960, 720) ?? null;
      return null;
    },
    elementsFromPoint(x: number, y: number) {
      return options.elementsFromPoint ? options.elementsFromPoint(x, y) : [];
    },
    elementFromPoint(x: number, y: number) {
      return options.elementFromPoint ? options.elementFromPoint(x, y) : options.elementsFromPoint?.(x, y)[0] ?? null;
    },
    activeElement: body,
    dispatchEvent(event: { type: string; key?: string }): boolean {
      (document as unknown as { dispatchedEvents: string[] }).dispatchedEvents.push(event.key ? `${event.type}:${event.key}` : event.type);
      return true;
    }
  } as unknown as Document;

  Object.defineProperty(globalThis, "MouseEvent", {
    configurable: true,
    value: class FakeMouseEvent {
      type: string;
      constructor(type: string) {
        this.type = type;
      }
    }
  });
  Object.defineProperty(globalThis, "KeyboardEvent", {
    configurable: true,
    value: class FakeKeyboardEvent {
      type: string;
      key: string | undefined;
      constructor(type: string, init?: { key?: string }) {
        this.type = type;
        this.key = init?.key;
      }
    }
  });
  Object.defineProperty(globalThis, "WheelEvent", {
    configurable: true,
    value: class FakeWheelEvent {
      type: string;
      constructor(type: string) {
        this.type = type;
      }
    }
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      dispatchedEvents: [] as string[],
      location: { href: options.href, search: new URL(options.href).search },
      innerWidth: viewportWidth,
      innerHeight: viewportHeight,
      getComputedStyle: (element: FakeElement) => ({
        display: element.style.display ?? "block",
        visibility: element.style.visibility ?? "visible",
        opacity: element.style.opacity ?? "1"
      }),
      dispatchEvent(event: { type: string; key?: string }): boolean {
        this.dispatchedEvents.push(event.key ? `${event.type}:${event.key}` : event.type);
        return true;
      }
    }
  });

  return document;
}

function calibrationFor(points: Record<"like_count" | "comment_count" | "favorite_count" | "share_count", { x: number; y: number }> & { next_video_button?: { x: number; y: number } }, viewportWidth = 1000, viewportHeight = 900): RightRailCalibration {
  return {
    version: points.next_video_button ? "phase12a_calibrated_five_point_workflow" : "calibrated_four_point_workflow",
    viewport_width: viewportWidth,
    viewport_height: viewportHeight,
    points: {
      like_count: { x: points.like_count.x, y: points.like_count.y, x_ratio: points.like_count.x / viewportWidth, y_ratio: points.like_count.y / viewportHeight },
      comment_count: { x: points.comment_count.x, y: points.comment_count.y, x_ratio: points.comment_count.x / viewportWidth, y_ratio: points.comment_count.y / viewportHeight },
      favorite_count: { x: points.favorite_count.x, y: points.favorite_count.y, x_ratio: points.favorite_count.x / viewportWidth, y_ratio: points.favorite_count.y / viewportHeight },
      share_count: { x: points.share_count.x, y: points.share_count.y, x_ratio: points.share_count.x / viewportWidth, y_ratio: points.share_count.y / viewportHeight },
      ...(points.next_video_button ? { next_video_button: { x: points.next_video_button.x, y: points.next_video_button.y, x_ratio: points.next_video_button.x / viewportWidth, y_ratio: points.next_video_button.y / viewportHeight } } : {})
    },
    created_at: new Date().toISOString(),
    profile_url_host: "www.douyin.com"
  };
}

{
  const document = createFakeDocument({ href: "https://www.douyin.com/user/test?modal_id=7634192733514501417&showSubTab=video" });
  assert.equal(detectCurrentAwemeId("https://www.douyin.com/user/test?modal_id=7634192733514501417&showSubTab=video", document), "7634192733514501417");
}

{
  const document = createFakeDocument({ href: "https://www.douyin.com/video/7634192733514501417" });
  assert.equal(detectCurrentAwemeId("https://www.douyin.com/video/7634192733514501417", document), "7634192733514501417");
}

{
  assert.equal(parseCompactCountFromOcr("46"), 46);
  assert.equal(parseCompactCountFromOcr("2.2万"), 22000);
  assert.equal(parseCompactCountFromOcr("00:22"), null);
  assert.equal(parseCompactCountFromOcr("豆瓣9.8"), null);
}

{
  const counts = {
    like_count: new FakeElement("span", "684", { x: 910, y: 300, width: 34, height: 20 }),
    comment_count: new FakeElement("span", "46", { x: 910, y: 380, width: 28, height: 20 }),
    favorite_count: new FakeElement("span", "151", { x: 910, y: 460, width: 32, height: 20 }),
    share_count: new FakeElement("span", "90", { x: 910, y: 540, width: 24, height: 20 })
  };
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    elementsFromPoint(x, y) {
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 300) <= 12) return [counts.like_count];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 380) <= 12) return [counts.comment_count];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 460) <= 12) return [counts.favorite_count];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 540) <= 12) return [counts.share_count];
      return [];
    }
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const pointMetrics = readCalibratedPointMetrics(document, calibration);
  assert.equal(pointMetrics.point_results.like_count?.value, 684);
  assert.equal(pointMetrics.point_results.comment_count?.value, 46);
  assert.equal(pointMetrics.point_results.favorite_count?.value, 151);
  assert.equal(pointMetrics.point_results.share_count?.value, 90);
  assert.equal(pointMetrics.source_used, "calibrated_point_dom");
}

{
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    viewportWidth: 1200,
    viewportHeight: 1000,
    elementsFromPoint(x, y) {
      if (Math.abs(x - 1092) <= 12 && Math.abs(y - 333) <= 12) return [new FakeElement("span", "684", { x: 1092, y: 333, width: 34, height: 20 })];
      if (Math.abs(x - 1092) <= 12 && Math.abs(y - 422) <= 12) return [new FakeElement("span", "46", { x: 1092, y: 422, width: 28, height: 20 })];
      if (Math.abs(x - 1092) <= 12 && Math.abs(y - 511) <= 12) return [new FakeElement("span", "151", { x: 1092, y: 511, width: 32, height: 20 })];
      if (Math.abs(x - 1092) <= 12 && Math.abs(y - 600) <= 12) return [new FakeElement("span", "90", { x: 1092, y: 600, width: 24, height: 20 })];
      return [];
    }
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const pointMetrics = readCalibratedPointMetrics(document, calibration);
  assert.equal(pointMetrics.point_results.like_count?.value, 684);
  assert.equal(pointMetrics.point_results.comment_count?.value, 46);
}

{
  const video = new FakeVideoElement(563.3, false, { x: 600, y: 100, width: 320, height: 640 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    videos: [video],
    elementsFromPoint: () => [new FakeElement("span", "豆瓣9.8", { x: 910, y: 300, width: 60, height: 20 })]
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const probe = probeCurrentModalMetrics(document, globalThis.window.location as Location, calibration);
  assert.equal(probe.probe_status, "WARN");
  assert.equal(probe.like_count, null);
}

{
  const video = new FakeVideoElement(563.3, false, { x: 600, y: 100, width: 320, height: 640 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/user/test?modal_id=7634192733514501417",
    videos: [video],
    elementsFromPoint(x, y) {
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 300) <= 12) return [new FakeElement("span", "684", { x: 910, y: 300, width: 34, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 380) <= 12) return [new FakeElement("span", "46", { x: 910, y: 380, width: 28, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 460) <= 12) return [new FakeElement("span", "151", { x: 910, y: 460, width: 32, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 540) <= 12) return [new FakeElement("span", "90", { x: 910, y: 540, width: 24, height: 20 })];
      return [];
    }
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const metrics = extractCurrentModalMetricsForAweme(document, "7634192733514501417", null, null, null, null, calibration);
  assert.equal(metrics?.duration_seconds, 563.3);
  assert.equal(metrics?.like_count, 684);
  assert.equal(metrics?.comment_count, 46);
  assert.equal(metrics?.favorite_count, 151);
  assert.equal(metrics?.share_count, 90);
  assert.equal(metrics?.source_used, "calibrated_point_dom");

  const probe = probeCurrentModalMetrics(document, globalThis.window.location as Location, calibration);
  assert.equal(probe.probe_status, "PASS");
  assert.equal(probe.ready_for_full_harvest, true);
  const summary = buildDomDetailEvidenceSummary(metrics!);
  assert.equal(summary.evidence_collection_version, PRODUCTION_EVIDENCE_COLLECTION_VERSION, "production harvest payload uses backend-accepted phase11a evidence version");
  assert.notEqual(summary.evidence_collection_version, "phase12a_calibrated_five_point_workflow", "production payload must not send phase12a transition version");
  assert.deepEqual(summary.evidence_sources, ["calibrated_point_modal_counts", "smart_capture_harvest"], "calibrated summary keeps modal-count and smart-harvest sources");
}

{
  const video = new FakeVideoElement(563.3, false, { x: 600, y: 100, width: 320, height: 640 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    videos: [video],
    elementsFromPoint(x, y) {
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 300) <= 12) return [new FakeElement("span", "684", { x: 910, y: 300, width: 34, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 380) <= 12) return [new FakeElement("span", "46", { x: 910, y: 380, width: 28, height: 20 })];
      return [];
    }
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const probe = probeCurrentModalMetrics(document, globalThis.window.location as Location, calibration);
  assert.equal(probe.probe_status, "WARN");
  assert.equal(probe.ready_for_full_harvest, false);
}

{
  const video = new FakeVideoElement(563.3, false, { x: 600, y: 100, width: 320, height: 640 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    videos: [video],
    elementsFromPoint(x, y) {
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 300) <= 12) return [new FakeElement("span", "684", { x: 910, y: 300, width: 34, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 380) <= 12) return [new FakeElement("span", "46", { x: 910, y: 380, width: 28, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 460) <= 12) return [new FakeElement("span", "151", { x: 910, y: 460, width: 32, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 540) <= 12) return [new FakeElement("span", "90", { x: 910, y: 540, width: 24, height: 20 })];
      return [];
    }
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const item = await waitForCurrentModalMetrics(document, globalThis.window.location as Location, "7634192733514501417", 20, calibration);
  assert.equal(item?.aweme_id, "7634192733514501417");
  assert.equal(item?.raw_dom_detail_metrics.like_count, 684);
}

{
  const video = new FakeVideoElement(563.3, false, { x: 600, y: 100, width: 320, height: 640 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    videos: [video],
    elementsFromPoint(x, y) {
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 300) <= 12) return [new FakeElement("span", "684", { x: 910, y: 300, width: 34, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 380) <= 12) return [new FakeElement("span", "46", { x: 910, y: 380, width: 28, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 460) <= 12) return [new FakeElement("span", "151", { x: 910, y: 460, width: 32, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 540) <= 12) return [new FakeElement("span", "90", { x: 910, y: 540, width: 24, height: 20 })];
      return [];
    }
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const savedStates: StoredFullModalHarvestState[] = [];
  const context: CaptureContext = { page_url: globalThis.window.location.href, captured_at: new Date().toISOString() };
  const controller = new FullModalHarvestController(
    document,
    globalThis.window.location as Location,
    context,
    {
      target_count: 1,
      delay_between_items_ms: 5000,
      per_item_timeout_ms: 50,
      flush_every_n_items: 1,
      stop_on_captcha: true,
      stop_on_no_next: true,
      allow_probe_warnings: false,
      capture_session_id: null,
      capture_id: null,
      target_aweme_ids: [],
      retry_failed_only: false,
      profile_card_evidence_by_aweme_id: {},
      apiBaseUrl: "http://127.0.0.1:8000",
      captureSessionId: null
    },
    {
      flushBatch: async () => ({ ok: true, harvest_response: { updated_count: 1, unchanged_count: 0, failed_count: 0, matched_count: 1, unmatched_count: 0, flushed_aweme_ids: ["7634192733514501417"], failure_summaries: [] } }),
      saveState: async (state) => {
        savedStates.push(state);
      },
      clearState: async () => undefined,
      getCalibration: async () => calibration,
      captureVisibleTab: async () => null
    }
  );
  await controller.bootstrapCurrentItem();
  assert.equal(controller.progress.harvested_count, 1);
  assert.equal(controller.progress.last_extracted_metrics?.source_used, "calibrated_point_dom");
  assert.ok(savedStates.length >= 1);
}

{
  const video = new FakeVideoElement(563.3, false, { x: 600, y: 100, width: 320, height: 640 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    videos: [video],
    elementsFromPoint(x, y) {
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 300) <= 12) return [new FakeElement("span", "684", { x: 910, y: 300, width: 34, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 380) <= 12) return [new FakeElement("span", "46", { x: 910, y: 380, width: 28, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 460) <= 12) return [new FakeElement("span", "151", { x: 910, y: 460, width: 32, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 540) <= 12) return [new FakeElement("span", "90", { x: 910, y: 540, width: 24, height: 20 })];
      return [];
    }
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const savedStates: StoredFullModalHarvestState[] = [];
  let flushAttempts = 0;
  const controller = new FullModalHarvestController(
    document,
    globalThis.window.location as Location,
    { page_url: globalThis.window.location.href, captured_at: new Date().toISOString() },
    {
      target_count: 1,
      delay_between_items_ms: 0,
      per_item_timeout_ms: 20,
      flush_every_n_items: 1,
      stop_on_captcha: true,
      stop_on_no_next: true,
      allow_probe_warnings: false,
      capture_session_id: "session-13g",
      capture_id: null,
      target_aweme_ids: [],
      retry_failed_only: false,
      profile_card_evidence_by_aweme_id: {},
      apiBaseUrl: "http://127.0.0.1:8000",
      captureSessionId: "session-13g"
    },
    {
      flushBatch: async () => {
        flushAttempts += 1;
        return {
          ok: false,
          backend_post: {
            ok: false,
            url: "http://127.0.0.1:8000/douyin-extension/full-modal-harvest",
            status_code: null,
            error_code: "backend_unreachable",
            error_message: "backend_unreachable: backend health check failed before flush response",
            retryable: true
          }
        };
      },
      saveState: async (state) => {
        savedStates.push(state);
      },
      clearState: async () => undefined,
      getCalibration: async () => calibration,
      captureVisibleTab: async () => null
    }
  );

  const result = await controller.start();
  const snapshot = controller.snapshotState();
  assert.equal(flushAttempts, 3, "retryable backend flush failure is attempted three times before pausing");
  assert.equal(result.harvest_status, "paused", "flush failure pauses instead of failing extraction/navigation");
  assert.equal(result.last_flush_status, "queued", "failed flush remains queued for operator retry");
  assert.equal(result.flush_error_code, "backend_unreachable");
  assert.match(result.flush_next_action ?? "", /Retry Flush Pending/);
  assert.equal(result.pending_count, 1, "harvested item remains pending after failed flush");
  assert.equal(snapshot.pending_flush_queue?.[0]?.status, "failed_retryable", "persistent queue preserves retryable item state");
  assert.equal(snapshot.pending_flush_queue?.[0]?.attempts, 1, "queue attempt counter records the flush cycle without dropping the item");
  assert.equal(savedStates.some((state) => state.pending_flush_queue?.some((item) => item.aweme_id === "7634192733514501417")), true, "pending flush queue is persisted with controller state");
}

{
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 },
    next_video_button: { x: 960, y: 720 }
  });
  assert.equal(calibration.version, "phase12a_calibrated_five_point_workflow", "legacy five-point calibration can still be represented for compatibility");
  assert.equal(calibration.points.next_video_button?.x_ratio, 0.96, "legacy calibration can store next_video_button as optional point");
}

{
  const nextButton = new FakeElement("button", "next", { x: 960, y: 720, width: 40, height: 40 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    elementFromPoint(x, y) {
      if (x === 960 && y === 720) return nextButton;
      return null;
    }
  });
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 },
    next_video_button: { x: 960, y: 720 }
  });
  const click = clickCalibratedNextPoint(document, calibration);
  assert.deepEqual(click, { x: 960, y: 720, clicked: true }, "next navigation clicks calibrated coordinate");
  assert.deepEqual(nextButton.dispatchedEvents, ["pointerdown", "mousedown", "pointerup", "mouseup", "click"], "calibrated next click dispatches pointer/mouse sequence");
}

{
  const nextButton = new FakeElement("button", "next", { x: 960, y: 720, width: 40, height: 40 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    elementFromPoint(x, y) {
      if (x === 960 && y === 720) return nextButton;
      return null;
    }
  });
  const location = { href: "https://www.douyin.com/video/7634192733514501417" } as Location;
  const result = await navigateNextModalAutomatically(document, location, "7634192733514501417", 20);
  assert.equal(result.reason, "navigation_timeout", "automatic navigation times out only after restored fallback attempts");
  assert.equal(result.failed_stage, "modal_id_change_timeout");
  assert.equal(nextButton.dispatchedEvents.includes("click"), true, "restored navigation tries existing modal next control before keyboard fallbacks");
  assert.equal((globalThis.window as unknown as FakeElement).dispatchedEvents.includes("keydown:ArrowDown"), true, "restored navigation sends ArrowDown to window-level Douyin handlers");
  assert.equal((document as unknown as FakeElement).dispatchedEvents.includes("keydown:ArrowDown"), true, "restored navigation also sends ArrowDown to document-level handlers");
  assert.equal((document.body as unknown as FakeElement).dispatchedEvents.includes("wheel"), true, "restored navigation keeps wheel fallback");
}

{
  let current = "7634192733514501417";
  const changed = await waitForModalIdChange(() => {
    current = "7634192733514509999";
    return current;
  }, "7634192733514501417", 20);
  assert.equal(changed, true, "modal_id change after click continues harvest");
}

{
  const document = createFakeDocument({ href: "https://www.douyin.com/video/7634192733514501417?modal_id=7634192733514501417" });
  const location = { href: "https://www.douyin.com/video/7634192733514501417?modal_id=7634192733514501417", search: "?modal_id=7634192733514501417" } as Location;
  const result = await navigateDirectlyToTargetModal(location, document, "7634192733514501417", "7634192733514509999", 20);
  assert.equal(result.moved, true, "target queue navigation first routes directly to next modal_id");
  assert.equal(result.target_aweme_id, "7634192733514509999", "direct route records the queued target aweme id");
  assert.match(location.href, /modal_id=7634192733514509999/, "direct route updates modal_id before fallback navigation is needed");
}

{
  const document = createFakeDocument({ href: "https://www.douyin.com/video/7634192733514501417" });
  const location = { href: "https://www.douyin.com/video/7634192733514501417" } as Location;
  const result = await navigateNextVideoByCalibratedPoint(
    document,
    location,
    calibrationFor({
      like_count: { x: 910, y: 300 },
      comment_count: { x: 910, y: 380 },
      favorite_count: { x: 910, y: 460 },
      share_count: { x: 910, y: 540 }
    }),
    "7634192733514501417",
    20
  );
  assert.equal(result.reason, "navigation_timeout", "four-point harvest attempts automatic navigation before timing out");
  assert.equal(result.failed_stage, "modal_id_change_timeout");
}

{
  const video = new FakeVideoElement(563.3, false, { x: 600, y: 100, width: 320, height: 640 });
  const document = createFakeDocument({
    href: "https://www.douyin.com/video/7634192733514501417",
    videos: [video],
    elementsFromPoint(x, y) {
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 300) <= 12) return [new FakeElement("span", "684", { x: 910, y: 300, width: 34, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 380) <= 12) return [new FakeElement("span", "46", { x: 910, y: 380, width: 28, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 460) <= 12) return [new FakeElement("span", "151", { x: 910, y: 460, width: 32, height: 20 })];
      if (Math.abs(x - 910) <= 12 && Math.abs(y - 540) <= 12) return [new FakeElement("span", "90", { x: 910, y: 540, width: 24, height: 20 })];
      return [];
    }
  });
  const location = globalThis.window.location as Location;
  const calibration = calibrationFor({
    like_count: { x: 910, y: 300 },
    comment_count: { x: 910, y: 380 },
    favorite_count: { x: 910, y: 460 },
    share_count: { x: 910, y: 540 }
  });
  const savedStates: StoredFullModalHarvestState[] = [];
  const controller = new FullModalHarvestController(
    document,
    location,
    { page_url: location.href, captured_at: new Date().toISOString() },
    {
      target_count: 2,
      delay_between_items_ms: 0,
      per_item_timeout_ms: 20,
      flush_every_n_items: 10,
      stop_on_captcha: true,
      stop_on_no_next: true,
      allow_probe_warnings: false,
      capture_session_id: null,
      capture_id: null,
      target_aweme_ids: [],
      retry_failed_only: false,
      profile_card_evidence_by_aweme_id: {},
      apiBaseUrl: "http://127.0.0.1:8000",
      captureSessionId: null
    },
    {
      flushBatch: async () => ({ ok: true, harvest_response: { updated_count: 0, unchanged_count: 0, failed_count: 0, matched_count: 0, unmatched_count: 0, flushed_aweme_ids: ["7634192733514501417"], failure_summaries: [] } }),
      saveState: async (state) => {
        savedStates.push(state);
      },
      clearState: async () => undefined,
      getCalibration: async () => calibration,
      captureVisibleTab: async () => null
    }
  );
  const progress = await controller.start();
  assert.equal(savedStates.some((state) => state.phase === "queued_item" && state.harvested_aweme_ids.length === 1), true, "after successful extraction, phase changes from extracting_metrics to queued_item");
  assert.equal(savedStates.some((state) => state.phase === "loading_next_video" || state.phase === "waiting_modal_change"), true, "after queued_item, navigation is attempted");
  assert.equal(progress.stopped_reason, "navigation_timeout", "navigation timeout flushes pending and stops safely");
  assert.equal(progress.last_error, "Press ArrowDown manually or click next video, then Resume Harvest.");
  assert.equal(progress.flushed_count, 1, "pending item is flushed on navigation timeout finalizer");
}

{
  const source = await import("node:fs").then((fs) => fs.readFileSync(new URL("./modalHarvest.ts", import.meta.url), "utf8"));
  assert.match(source, /private isHarvestComplete\(\): boolean/, "Phase 12H has one completion guard");
  assert.match(source, /processedTargetCount\(\) >= targetCount/, "completion guard supports processed_count >= target_count");
  assert.match(source, /this\.targetAwemeIds\.every/, "completion guard supports all target_aweme_ids processed via target status map");
  assert.match(source, /completeIfHarvestComplete\(\)/, "completion guard runs after extraction, queueing, flush, failure marking, before navigation, and resume load");
  assert.match(source, /this\.targetAwemeIds\.length > 0 && !this\.nextTargetAwemeId\(awemeId\)/, "target_index=target_count does not attempt navigateNext for target queues");
  assert.match(source, /const flushResult = await this\.flushInternal\(\)/, "final item completion runs final flush before completed state");
  assert.match(source, /this\.phase = this\.failedTargetCount\(\) > 0 \? "completed_with_warnings" : "completed"/, "completion state distinguishes completed and completed_with_warnings");
  assert.match(source, /this\.running = false;\s*return this\.progress;/, "resume with all targets processed immediately completes and stops running");
  assert.doesNotMatch(source, /if \(this\.processedTargetCount\(\) >= this\.effectiveTargetCount\(\)\) break;/, "final target does not only break and leave phase extracting_metrics");
  assert.match(source, /alreadyProcessedQueueTarget && this\.consecutiveDuplicateCount >= 3/, "duplicate loop is capped but does not inflate current index or stop before routing to next target");
  assert.match(source, /if \(this\.lastNavigationAttemptFromAwemeId\)/, "duplicate_count increments only after navigation attempt");
  assert.match(source, /nextTargetAwemeId\(awemeId\)/, "duplicate target routes to next unprocessed target");
  assert.doesNotMatch(source, /bootstrapNavigation = await this\.navigateAfterItem/, "start loop must not pre-bootstrap and return stuck queued Video 1 state");
  assert.match(source, /flushInternal\(\)/, "navigation timeout path still flushes pending in finalizer");
}

{
  const ok = auditHarvestRecentItemsIntegrity(
    [{ aweme_id: "7634192733514501417", duration_seconds: null, like_count: null, comment_count: null, favorite_count: null, share_count: null, extraction_warning: null, status: "ok" }],
    "7634192733514501417"
  );
  assert.deepEqual(ok, { ok: true }, "integrity audit passes when latest recent item matches expected aweme");
}

{
  const mismatch = auditHarvestRecentItemsIntegrity(
    [{ aweme_id: "7634192733514509999", duration_seconds: null, like_count: null, comment_count: null, favorite_count: null, share_count: null, extraction_warning: null, status: "ok" }],
    "7634192733514501417"
  );
  assert.deepEqual(
    mismatch,
    { ok: false, observedAwemeId: "7634192733514509999", reason: "recent_item_aweme_id_mismatch" },
    "integrity audit fails with mismatch reason when latest recent item differs"
  );
}

{
  const source = await import("node:fs").then((fs) => fs.readFileSync(new URL("./modalHarvest.ts", import.meta.url), "utf8"));
  const typesSource = await import("node:fs").then((fs) => fs.readFileSync(new URL("./types.ts", import.meta.url), "utf8"));
  assert.match(typesSource, /target_aweme_id\?: string \| null/);
  assert.match(typesSource, /modal_aweme_id_before_extract\?: string \| null/);
  assert.match(typesSource, /modal_aweme_id_after_extract\?: string \| null/);
  assert.match(typesSource, /extracted_aweme_id\?: string \| null/);
  assert.match(source, /metricSignature\(/);
  assert.match(source, /buildIntegrityBoundItem\(/);
  assert.match(source, /metric_numeric_invalid/);
}

console.log("full modal calibrated point tests passed");


