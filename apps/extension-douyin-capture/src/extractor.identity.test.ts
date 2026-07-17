import assert from "node:assert/strict";
import { discoverGridVideos, extractVideos, filterNetworkItemsForContext } from "./extractor";
import { normalizeDouyinNetworkPayload } from "./networkCache";
import type { CaptureContext, NetworkVideoMetadata } from "./types";

type AttributeRecord = { name: string; value: string };

class FakeElement {
  readonly dataset: Record<string, string> = {};
  readonly style = { backgroundImage: "" };
  readonly attributes: AttributeRecord[] = [];
  parentElement: FakeElement | null = null;
  textContent = "";
  title = "";

  constructor(
    readonly tagName: string,
    private readonly attrs: Record<string, string> = {},
    private readonly children: FakeElement[] = []
  ) {
    this.attributes = Object.entries(attrs).map(([name, value]) => ({ name, value }));
    this.textContent = attrs.textContent ?? "";
    this.title = attrs.title ?? "";
    if (attrs.styleBackgroundImage) this.style.backgroundImage = attrs.styleBackgroundImage;
    for (const [key, value] of Object.entries(attrs)) {
      if (key.startsWith("dataset.")) this.dataset[key.slice("dataset.".length)] = value;
    }
    for (const child of children) child.parentElement = this;
  }

  get href(): string {
    return this.attrs.href ?? "";
  }

  get src(): string {
    return this.attrs.src ?? "";
  }

  get currentSrc(): string {
    return this.attrs.currentSrc ?? this.attrs.src ?? "";
  }

  get srcset(): string {
    return this.attrs.srcset ?? "";
  }

  get poster(): string {
    return this.attrs.poster ?? "";
  }

  getAttribute(name: string): string | null {
    return this.attrs[name] ?? null;
  }

  matches(selector: string): boolean {
    return selector.split(",").map((entry) => entry.trim()).includes(this.tagName.toLowerCase());
  }

  closest(): FakeElement | null {
    return this.parentElement;
  }

  querySelector(selector: string): FakeElement | null {
    return this.querySelectorAll(selector)[0] ?? null;
  }

  querySelectorAll(selector: string): FakeElement[] {
    const descendants = this.descendants();
    if (selector === "img") return descendants.filter((element) => element.tagName === "img");
    if (selector === "img, picture, video[poster], source[srcset]") return descendants.filter((element) => element.tagName === "img" || element.tagName === "picture" || (element.tagName === "video" && Boolean(element.getAttribute("poster"))) || (element.tagName === "source" && Boolean(element.getAttribute("srcset"))));
    if (selector === "source[srcset]") return descendants.filter((element) => element.tagName === "source" && Boolean(element.getAttribute("srcset")));
    if (selector === "video[poster]") return descendants.filter((element) => element.tagName === "video" && Boolean(element.getAttribute("poster")));
    if (selector === "*") return descendants;
    if (selector === 'a[href*="/video/"]') return descendants.filter((element) => element.tagName === "a" && element.href.includes("/video/"));
    return [];
  }

  getBoundingClientRect(): { width: number; height: number } {
    return { width: 240, height: 320 };
  }

  private descendants(): FakeElement[] {
    const values: FakeElement[] = [];
    const visit = (element: FakeElement): void => {
      for (const child of element.children) {
        values.push(child);
        visit(child);
      }
    };
    visit(this);
    return values;
  }
}

class FakeDocument {
  constructor(private readonly links: FakeElement[]) {}

  querySelectorAll(selector: string): FakeElement[] {
    if (selector === 'a[href*="/video/"]') return this.links;
    return [];
  }
}

function makeVideoLink(awemeId: string, title: string, domThumbnailUrl?: string): FakeElement {
  const thumbnail = domThumbnailUrl ? new FakeElement("img", { src: domThumbnailUrl }) : null;
  const link = new FakeElement("a", {
    href: `https://www.douyin.com/video/${awemeId}`,
    title,
    textContent: title
  }, thumbnail ? [thumbnail] : []);
  new FakeElement("article", { textContent: title }, [link]);
  return link;
}

function makeSharedGridTile(awemeId: string, title: string, domThumbnailUrl: string): FakeElement {
  const thumbnail = new FakeElement("img", { src: domThumbnailUrl });
  const link = new FakeElement("a", { href: `https://www.douyin.com/video/${awemeId}` }, [thumbnail]);
  new FakeElement("article", { textContent: title }, [link]);
  return link;
}

const sharedNetworkUrlList = ["https://p3.douyinpic.com/obj/shared-source-list.jpeg"];
const networkItems: NetworkVideoMetadata[] = [
  {
    aweme_id: "7420000000000000102",
    title: "Network title 102",
    thumbnail_url: "https://p3.douyinpic.com/obj/network-102.jpeg",
    url_list: sharedNetworkUrlList,
    view_count: 102,
    view_count_text: "102",
    like_count: 1202,
    like_count_text: "1202",
    comment_count: 2202,
    comment_count_text: "2202",
    duration_seconds: 22,
    duration_text: "00:22",
    posted_at: "2026-04-27T10:22:00.000Z",
    raw_source: "network_json",
    raw_network_aweme: { aweme_id: "7420000000000000102", statistics: { play_count: 102 } }
  },
  {
    aweme_id: "7420000000000000101",
    title: "Network title 101",
    thumbnail_url: "https://p3.douyinpic.com/obj/network-101.jpeg",
    url_list: sharedNetworkUrlList,
    view_count: 101,
    view_count_text: "101",
    like_count: 1101,
    like_count_text: "1101",
    comment_count: 2101,
    comment_count_text: "2101",
    duration_seconds: 11,
    duration_text: "00:11",
    posted_at: "2026-04-27T10:11:00.000Z",
    raw_source: "network_json",
    raw_network_aweme: { aweme_id: "7420000000000000101", statistics: { play_count: 101 } }
  },
  {
    aweme_id: "7420000000000000103",
    title: "Network title 103",
    thumbnail_url: "https://p3.douyinpic.com/obj/network-103.jpeg",
    url_list: sharedNetworkUrlList,
    view_count: 103,
    view_count_text: "103",
    like_count: 1303,
    like_count_text: "1303",
    comment_count: 2303,
    comment_count_text: "2303",
    duration_seconds: 33,
    duration_text: "00:33",
    posted_at: "2026-04-27T00:00:00.000Z",
    raw_source: "network_json",
    raw_network_aweme: { aweme_id: "7420000000000000103", statistics: { play_count: 103 } }
  },
  {
    aweme_id: "9999999999999999999",
    title: "Mismatched network title must not merge",
    thumbnail_url: "https://p3.douyinpic.com/obj/mismatch.jpeg",
    url_list: ["https://p3.douyinpic.com/obj/mismatch.jpeg"],
    view_count: 999,
    like_count: 1999,
    comment_count: 2999,
    duration_seconds: 999,
    duration_text: "16:39",
    posted_at: "2026-04-27T10:59:00.000Z",
    raw_source: "network_json"
  },
  {
    aweme_id: "",
    title: "Missing id network title must not merge",
    thumbnail_url: "https://p3.douyinpic.com/obj/missing-id.jpeg",
    url_list: ["https://p3.douyinpic.com/obj/missing-id.jpeg"],
    view_count: 888,
    like_count: 1888,
    comment_count: 2888,
    duration_seconds: 888,
    duration_text: "14:48",
    posted_at: "2026-04-27T10:58:00.000Z",
    raw_source: "network_json"
  },
  {
    aweme_id: "7420000000000000104",
    title: "Network title 104 without thumbnail",
    raw_source: "network_json"
  }
];

const fakeDocument = new FakeDocument([
  makeVideoLink("7420000000000000101", "DOM title 101 01:01 2026-04-26 11:01 播放 401 赞 41 评论 1", "https://p3.douyinpic.com/obj/dom-101.jpeg"),
  makeVideoLink("7420000000000000102", "DOM title 102 02:02 2026-04-26 11:02 播放 402 赞 42 评论 2", "https://p3.douyinpic.com/obj/dom-102.jpeg"),
  makeVideoLink("7420000000000000103", "DOM title 103 03:03 2026-04-26 11:03 播放 403 赞 43 评论 3", "https://p3.douyinpic.com/obj/dom-103.jpeg"),
  makeVideoLink("7420000000000000104", "DOM title 104 04:04 2026-04-26 11:04 播放 404 赞 44 评论 4", "https://p3.douyinpic.com/obj/dom-104.jpeg")
]) as unknown as Document;
(globalThis as unknown as { document: Document }).document = {
  ...fakeDocument,
  body: new FakeElement("body") as unknown as HTMLElement,
  documentElement: new FakeElement("html") as unknown as HTMLElement
} as Document;

const discoveries = discoverGridVideos(fakeDocument);
assert.deepEqual(discoveries.map((item) => item.aweme_id), ["7420000000000000101", "7420000000000000102", "7420000000000000103", "7420000000000000104"], "Grid discovery must return distinct aweme_ids in visible order");
assert.deepEqual(discoveries.map((item) => item.source_url), ["https://www.douyin.com/video/7420000000000000101", "https://www.douyin.com/video/7420000000000000102", "https://www.douyin.com/video/7420000000000000103", "https://www.douyin.com/video/7420000000000000104"], "Grid discovery must keep source URLs only as discovery identity data");
assert.deepEqual(discoveries.map((item) => item.visible_order), [0, 1, 2, 3], "Grid discovery must preserve visible order without assigning metadata truth");
assert.equal(Object.prototype.hasOwnProperty.call(discoveries[0] as unknown as Record<string, unknown>, "title"), false, "Grid discovery records must not expose title as primary metadata");
assert.equal(Object.prototype.hasOwnProperty.call(discoveries[0] as unknown as Record<string, unknown>, "thumbnail_url"), false, "Grid discovery records must not expose thumbnail as primary metadata");
assert.equal(Object.prototype.hasOwnProperty.call(discoveries[0] as unknown as Record<string, unknown>, "view_count"), false, "Grid discovery records must not expose stats as primary metadata");

const duplicateDiagnostics = {
  active_grid_root_strategy: "unknown",
  candidate_link_count: 0,
  eligible_tile_count: 0,
  deduped_aweme_count: 0,
  rejected_link_count: 0,
  rejected_reason_counts: {} as Record<string, number>
};
const duplicateDiscoveries = discoverGridVideos(
  new FakeDocument([
    makeVideoLink("7420000000000000101", "Duplicate A", "https://p3.douyinpic.com/obj/dup-a.jpeg"),
    makeVideoLink("7420000000000000101", "Duplicate B", "https://p3.douyinpic.com/obj/dup-b.jpeg"),
    makeVideoLink("7420000000000000102", "Unique", "https://p3.douyinpic.com/obj/dup-c.jpeg")
  ]) as unknown as Document,
  duplicateDiagnostics
);
assert.deepEqual(duplicateDiscoveries.map((item) => item.aweme_id), ["7420000000000000101", "7420000000000000102"], "Duplicate anchors for one aweme_id must not inflate discovery count");
assert.equal(duplicateDiagnostics.candidate_link_count, 3, "Candidate count must reflect raw scoped anchor count before dedupe");
assert.equal(duplicateDiagnostics.eligible_tile_count, 3, "Eligibility count must reflect accepted pre-dedupe links");
assert.equal(duplicateDiagnostics.deduped_aweme_count, 2, "Deduped count must reflect exact unique aweme_ids");
assert.equal(duplicateDiagnostics.rejected_reason_counts.duplicate_aweme_in_grid, 1, "Duplicate rejection reason must be tracked for count integrity");

const videos = extractVideos(fakeDocument, networkItems);

assert.deepEqual(videos.map((video) => video.aweme_id), ["7420000000000000101", "7420000000000000102", "7420000000000000103", "7420000000000000104"], "Visible DOM order must remain keyed by DOM aweme_id, not network list order");
assert.equal(videos[0]?.title, "Network title 101", "First visible DOM item must receive only its matching aweme_id network record");
assert.equal(videos[1]?.title, "Network title 102", "Second visible DOM item must receive only its matching aweme_id network record");
assert.equal(videos[2]?.title, "Network title 103", "Third visible DOM item must receive only its matching aweme_id network record");
assert.equal(videos[3]?.title, "Network title 104 without thumbnail", "Fourth visible DOM item may receive matching non-thumbnail network metadata while retaining DOM thumbnail fallback");
assert.equal(videos[0]?.view_count, 101, "View counts must not merge by index from the first network record");
assert.equal(videos[1]?.view_count, 102, "View counts must stay bound to the matching aweme_id");
assert.equal(videos[2]?.view_count, 103, "View counts must stay bound to the matching aweme_id");
assert.equal(videos[3]?.view_count, 404, "DOM view-count fallback must remain bound to the same aweme_id when matching network metadata has no stats");
assert.equal(videos[0]?.like_count, 1101, "First visible DOM item must receive only its matching aweme_id network like count");
assert.equal(videos[1]?.like_count, 1202, "Second visible DOM item must receive only its matching aweme_id network like count");
assert.equal(videos[2]?.like_count, 1303, "Third visible DOM item must receive only its matching aweme_id network like count");
assert.equal(videos[3]?.like_count, 44, "DOM like-count fallback must remain bound to the same aweme_id when matching network metadata has no stats");
assert.equal(videos[0]?.comment_count, 2101, "First visible DOM item must receive only its matching aweme_id network comment count");
assert.equal(videos[1]?.comment_count, 2202, "Second visible DOM item must receive only its matching aweme_id network comment count");
assert.equal(videos[2]?.comment_count, 2303, "Third visible DOM item must receive only its matching aweme_id network comment count");
assert.equal(videos[3]?.comment_count, 4, "DOM comment-count fallback must remain bound to the same aweme_id when matching network metadata has no stats");
assert.deepEqual(videos.map((video) => video.view_count), [101, 102, 103, 404], "View-count binding must not follow network list order or reuse one count across visible items");
assert.deepEqual(videos.map((video) => video.like_count), [1101, 1202, 1303, 44], "Like-count binding must not follow network list order or reuse one count across visible items");
assert.deepEqual(videos.map((video) => video.comment_count), [2101, 2202, 2303, 4], "Comment-count binding must not follow network list order or reuse one count across visible items");
assert.equal(videos.some((video) => video.view_count === 999 || video.view_count === 888), false, "Unmatched or missing-id network view counts must not fan out into visible DOM items");
assert.equal(videos.some((video) => video.like_count === 1999 || video.like_count === 1888), false, "Unmatched or missing-id network like counts must not fan out into visible DOM items");
assert.equal(videos.some((video) => video.comment_count === 2999 || video.comment_count === 2888), false, "Unmatched or missing-id network comment counts must not fan out into visible DOM items");
assert.deepEqual(videos.map((video) => video.statistics?.view_count), [101, 102, 103, 404], "Nested statistics view counts must match canonical item-local view_count values");
assert.deepEqual(videos.map((video) => video.statistics?.like_count), [1101, 1202, 1303, 44], "Nested statistics like counts must match canonical item-local like_count values");
assert.deepEqual(videos.map((video) => video.statistics?.comment_count), [2101, 2202, 2303, 4], "Nested statistics comment counts must match canonical item-local comment_count values");
assert.equal(videos[0]?.thumbnail_url, "https://p3.douyinpic.com/obj/network-101.jpeg", "First visible DOM item must receive only its matching aweme_id network thumbnail, not DOM or index-based thumbnail");
assert.equal(videos[1]?.thumbnail_url, "https://p3.douyinpic.com/obj/network-102.jpeg", "Second visible DOM item must receive only its matching aweme_id network thumbnail");
assert.equal(videos[2]?.thumbnail_url, "https://p3.douyinpic.com/obj/network-103.jpeg", "Third visible DOM item must receive only its matching aweme_id network thumbnail");
assert.equal(videos[3]?.thumbnail_url, "https://p3.douyinpic.com/obj/dom-104.jpeg", "DOM thumbnail fallback must remain bound to the same aweme_id when matching network metadata has no thumbnail");
assert.deepEqual(videos.map((video) => video.thumbnail_url), ["https://p3.douyinpic.com/obj/network-101.jpeg", "https://p3.douyinpic.com/obj/network-102.jpeg", "https://p3.douyinpic.com/obj/network-103.jpeg", "https://p3.douyinpic.com/obj/dom-104.jpeg"], "Thumbnail binding must not follow network list order or reuse one thumbnail across visible items");
assert.equal(videos.some((video) => video.thumbnail_url === "https://p3.douyinpic.com/obj/mismatch.jpeg"), false, "Unmatched network thumbnails must not fan out into visible DOM items");
assert.equal(videos.some((video) => video.thumbnail_url === "https://p3.douyinpic.com/obj/missing-id.jpeg"), false, "Missing-id network thumbnails must not merge into DOM items");
assert.equal(videos[0]?.thumbnail_source, "network_json", "Network thumbnail provenance must be explicit for first item");
assert.equal(videos[0]?.raw_network_aweme?.aweme_id, "7420000000000000101", "Raw network aweme evidence must attach only by exact aweme_id");
assert.equal(videos[1]?.raw_network_aweme?.aweme_id, "7420000000000000102", "Raw network aweme evidence must not follow network array order");
assert.equal(videos[2]?.raw_network_aweme?.aweme_id, "7420000000000000103", "Raw network aweme evidence must remain keyed by exact aweme_id");
assert.equal(videos.some((video) => video.raw_network_aweme?.aweme_id === "9999999999999999999"), false, "Mismatched raw network aweme evidence must not fan out into visible DOM items");
assert.equal(videos[0]?.raw_dom_snapshot?.aweme_id, "7420000000000000101", "Raw DOM snapshot must be item-local and keyed by discovery aweme_id");
assert.equal(videos[0]?.raw_evidence_summary?.has_network_aweme, true, "Raw evidence summary must report matched network evidence");
assert.equal(videos[0]?.raw_evidence_summary?.has_dom_snapshot, true, "Raw evidence summary must report item-local DOM evidence");

const activeContext: CaptureContext = {
  capture_id: "capture-current",
  tab_id: 11,
  page_url: "https://www.douyin.com/user/current-profile",
  page_url_normalized: "https://www.douyin.com/user/current-profile",
  profile_url: "https://www.douyin.com/user/current-profile",
  profile_external_id: "current-profile",
  captured_at: "2026-04-28T14:00:00.000Z",
  cache_scope_key: "https://www.douyin.com/user/current-profile|https://www.douyin.com/user/current-profile|current-profile"
};
const scopedItems = filterNetworkItemsForContext([
  {
    aweme_id: "7420000000000000101",
    title: "Current profile metadata",
    context: activeContext
  },
  {
    aweme_id: "7420000000000000102",
    title: "Other profile metadata must be rejected",
    context: {
      ...activeContext,
      page_url: "https://www.douyin.com/user/other-profile",
      page_url_normalized: "https://www.douyin.com/user/other-profile",
      profile_url: "https://www.douyin.com/user/other-profile",
      profile_external_id: "other-profile"
    }
  },
  {
    aweme_id: "7420000000000000103",
    title: "Other tab metadata must be rejected",
    context: { ...activeContext, tab_id: 99 }
  }
], activeContext);
assert.deepEqual(scopedItems.map((item) => item.aweme_id), ["7420000000000000101"], "Network cache metadata from another profile/page/tab must be rejected before hydration");
assert.equal(videos[3]?.thumbnail_source, "dom_fallback", "DOM fallback thumbnail provenance must be explicit when matching network metadata has no thumbnail");
assert.equal(videos[0]?.duration_seconds, 11, "First visible DOM item must receive only its matching aweme_id network duration, not DOM or index-based duration");
assert.equal(videos[1]?.duration_seconds, 22, "Second visible DOM item must receive only its matching aweme_id network duration");
assert.equal(videos[2]?.duration_seconds, 33, "Third visible DOM item must receive only its matching aweme_id network duration");
assert.equal(videos[3]?.duration_seconds, 244, "DOM duration fallback must remain bound to the same aweme_id when matching network metadata has no duration");
assert.deepEqual(videos.map((video) => video.duration_text), ["00:11", "00:22", "00:33", "04:04"], "Duration binding must not follow network list order or reuse one duration across visible items");
assert.equal(videos[0]?.posted_at, "2026-04-27T10:11:00.000Z", "First visible DOM item must receive only its matching non-default network posted timestamp");
assert.equal(videos[1]?.posted_at, "2026-04-27T10:22:00.000Z", "Second visible DOM item must receive only its matching non-default network posted timestamp");
assert.notEqual(videos[2]?.posted_at, "2026-04-27T00:00:00.000Z", "Default midnight network posted timestamps must be rejected instead of displayed as source truth");
assert.equal(videos[2]?.posted_source, "dom_text", "Invalid/default network posted timestamps must fall back to same-item DOM posted text");
assert.equal(videos[3]?.posted_source, "dom_text", "DOM posted fallback must remain bound to the same aweme_id when matching network metadata has no posted timestamp");
assert.equal(videos.some((video) => video.duration_seconds === 999 || video.duration_seconds === 888), false, "Unmatched or missing-id network durations must not fan out into visible DOM items");
assert.equal(videos.some((video) => video.posted_at === "2026-04-27T10:59:00.000Z" || video.posted_at === "2026-04-27T10:58:00.000Z"), false, "Unmatched or missing-id network posted timestamps must not merge into DOM items");
assert.equal(videos.some((video) => video.title === "Mismatched network title must not merge"), false, "Network items without a matching DOM aweme_id must not fan out into visible DOM items");
assert.equal(videos.some((video) => video.title === "Missing id network title must not merge"), false, "Network items with missing aweme_id must not merge into DOM items");

const sharedGridLinks = [
  makeSharedGridTile("7508570147947334964", "Local title 7508570147947334964", "https://p3.douyinpic.com/obj/local-7508570147947334964.jpeg"),
  makeSharedGridTile("7632149506821311763", "Local title 7632149506821311763", "https://p3.douyinpic.com/obj/local-7632149506821311763.jpeg"),
  makeSharedGridTile("7629583407210614031", "Local title 7629583407210614031", "https://p3.douyinpic.com/obj/local-7629583407210614031.jpeg")
];
new FakeElement(
  "div",
  {
    textContent: "Shared profile wrapper title must not fan out 01:23 2026-04-26 播放 999 赞 999 评论 999",
    styleBackgroundImage: "url(https://p3.douyinpic.com/obj/shared-wrapper-thumbnail.jpeg)",
    "dataset.cover": "https://p3.douyinpic.com/obj/shared-wrapper-cover.jpeg"
  },
  sharedGridLinks.map((link) => link.parentElement as FakeElement)
);
const sharedGridNetworkItems: NetworkVideoMetadata[] = [
  {
    aweme_id: "7508570147947334964",
    title: "Network title 7508570147947334964",
    thumbnail_url: "https://p3.douyinpic.com/obj/network-7508570147947334964.jpeg",
    view_count: 750,
    like_count: 751,
    comment_count: 752,
    raw_source: "network_json"
  },
  {
    aweme_id: "7632149506821311763",
    title: "Network title 7632149506821311763",
    thumbnail_url: "https://p3.douyinpic.com/obj/network-7632149506821311763.jpeg",
    view_count: 763,
    like_count: 764,
    comment_count: 765,
    raw_source: "network_json"
  },
  {
    aweme_id: "7629583407210614031",
    title: "Network title 7629583407210614031",
    thumbnail_url: "https://p3.douyinpic.com/obj/network-7629583407210614031.jpeg",
    view_count: 762,
    like_count: 763,
    comment_count: 764,
    raw_source: "network_json"
  }
];
const sharedGridVideos = extractVideos(new FakeDocument(sharedGridLinks) as unknown as Document, sharedGridNetworkItems);
assert.deepEqual(sharedGridVideos.map((video) => video.aweme_id), ["7508570147947334964", "7632149506821311763", "7629583407210614031"], "Shared-grid fixture must produce three distinct payload items keyed by aweme_id");
assert.deepEqual(sharedGridVideos.map((video) => video.title), ["Network title 7508570147947334964", "Network title 7632149506821311763", "Network title 7629583407210614031"], "Network JSON must be the primary metadata source for title by exact aweme_id");
assert.deepEqual(sharedGridVideos.map((video) => video.thumbnail_url), ["https://p3.douyinpic.com/obj/network-7508570147947334964.jpeg", "https://p3.douyinpic.com/obj/network-7632149506821311763.jpeg", "https://p3.douyinpic.com/obj/network-7629583407210614031.jpeg"], "Network JSON must be the primary metadata source for thumbnail by exact aweme_id");
assert.deepEqual(sharedGridVideos.map((video) => video.view_count), [750, 763, 762], "Network JSON must be the primary metadata source for stats by exact aweme_id");
assert.equal(sharedGridVideos.every((video) => video.thumbnail_source === "network_json"), true, "Network thumbnail provenance must override grid DOM fallback");
assert.equal(sharedGridVideos.some((video) => video.title?.includes("Shared profile wrapper") || video.title?.startsWith("Local title")), false, "No item may use shared or local grid title when exact network title exists");
assert.equal(sharedGridVideos.some((video) => video.thumbnail_url?.includes("shared-wrapper") || video.thumbnail_url?.includes("local-")), false, "No item may use shared or local grid thumbnail when exact network thumbnail exists");
assert.deepEqual(sharedGridVideos.map((video) => video.raw?.visible_text), ["Local title 7508570147947334964", "Local title 7632149506821311763", "Local title 7629583407210614031"], "Raw visible text may retain diagnostics, but canonical metadata must come from exact-id hydrate first");

const detailHydrateVideos = extractVideos(
  new FakeDocument([makeVideoLink("8880000000000000001", "DOM title should remain fallback 08:08 播放 8 赞 8 评论 8", "https://p3.douyinpic.com/obj/dom-888.jpeg")]) as unknown as Document,
  [{ aweme_id: "8880000000000000001", title: "Network title 888", raw_source: "network_json", raw_network_aweme: { aweme_id: "8880000000000000001", desc: "Network detail test" } }],
  [{ aweme_id: "8880000000000000001", thumbnail_url: "https://p3.douyinpic.com/obj/detail-888.jpeg", view_count: 888, like_count: 1888, comment_count: 2888, raw_source: "detail_hydrate", raw_detail_aweme: { aweme_id: "8880000000000000001", statistics: { play_count: 888 } } }]
);
assert.equal(detailHydrateVideos[0]?.title, "Network title 888", "Detail hydrate must not override an existing network title");
assert.equal(detailHydrateVideos[0]?.thumbnail_url, "https://p3.douyinpic.com/obj/detail-888.jpeg", "Detail hydrate must fill missing thumbnail after network JSON by exact aweme_id");
assert.equal(detailHydrateVideos[0]?.view_count, 888, "Detail hydrate must fill missing stats only for the target aweme_id");
assert.equal(detailHydrateVideos[0]?.thumbnail_source, "detail_hydrate", "Detail hydrate thumbnail provenance must be explicit");
assert.equal(detailHydrateVideos[0]?.raw?.detail_aweme_id, "8880000000000000001", "Detail hydrate diagnostics must expose exact matched aweme_id");
assert.equal(detailHydrateVideos[0]?.raw_network_aweme?.aweme_id, "8880000000000000001", "Network raw evidence must survive exact-id payload building");
assert.equal(detailHydrateVideos[0]?.raw_detail_aweme?.aweme_id, "8880000000000000001", "Detail raw evidence must attach only after exact aweme_id matching");
assert.equal(detailHydrateVideos[0]?.raw_evidence_summary?.has_detail_aweme, true, "Raw evidence summary must report exact detail hydrate evidence");

const originCoverNetworkItems = normalizeDouyinNetworkPayload({
  item_list: [
    {
      aweme_id: "8880000000000000002",
      desc: "Origin cover priority fixture",
      video: {
        cover: { url_list: ["https://p3.douyinpic.com/obj/cover-8882.jpeg"] },
        origin_cover: { url_list: ["https://p3.douyinpic.com/obj/origin-8882.jpeg"] },
        dynamic_cover: { url_list: ["https://p3.douyinpic.com/obj/dynamic-8882.jpeg"] }
      },
      statistics: { play_count: 1 }
    }
  ]
}, "network_cover_priority_fixture");
const originCoverVideos = extractVideos(
  new FakeDocument([makeVideoLink("8880000000000000002", "DOM title 8882", "https://p3.douyinpic.com/obj/dom-8882.jpeg")]) as unknown as Document,
  originCoverNetworkItems
);
assert.equal(originCoverVideos[0]?.thumbnail_url, "https://p3.douyinpic.com/obj/origin-8882.jpeg", "Exact-id network recovery must prefer video.origin_cover.url_list before video.cover.url_list");
assert.equal(originCoverVideos[0]?.thumbnail_source, "network_json", "Origin-cover network recovery must set network_json provenance");
assert.equal(originCoverVideos[0]?.thumbnail_missing_reason, null, "Recovered network thumbnails must not keep a missing reason");

const detailAliasVideos = extractVideos(
  new FakeDocument([makeVideoLink("8880000000000000003", "DOM title no thumbnail")]) as unknown as Document,
  [{ aweme_id: "8880000000000000003", title: "Network title without cover", raw_source: "network_json" }],
  normalizeDouyinNetworkPayload({
    item_list: [
      {
        aweme_id: "8880000000000000003",
        desc: "Detail poster alias fixture",
        video: { poster_url: { url_list: ["https://p3.douyinpic.com/obj/detail-poster-8883.jpeg"] } },
        statistics: { play_count: 1 }
      }
    ]
  }, "detail_hydrate")
);
assert.equal(detailAliasVideos[0]?.thumbnail_url, "https://p3.douyinpic.com/obj/detail-poster-8883.jpeg", "Detail hydrate must recover equivalent poster fields by exact aweme_id when network lacks cover");
assert.equal(detailAliasVideos[0]?.thumbnail_source, "detail_hydrate", "Detail hydrate alias recovery must set detail provenance");
assert.equal(detailAliasVideos[0]?.thumbnail_missing_reason, null, "Recovered detail thumbnails must not keep a missing reason");

const localDomFallbackVideos = extractVideos(
  new FakeDocument([makeVideoLink("8880000000000000004", "DOM title dataset thumbnail", undefined)]) as unknown as Document,
  [{ aweme_id: "8880000000000000004", title: "Network title without thumbnail", raw_source: "network_json" }]
);
assert.equal(localDomFallbackVideos[0]?.thumbnail_url, null, "No DOM thumbnail should be invented when the local card has no image candidate");
assert.equal(localDomFallbackVideos[0]?.thumbnail_source, "missing", "All-failed thumbnail recovery must be marked missing");
assert.equal(localDomFallbackVideos[0]?.thumbnail_missing_reason, "detail_hydrate_not_run", "Missing debug reason must report that detail hydrate was not available before DOM also failed");

const detailNoCoverVideos = extractVideos(
  new FakeDocument([makeVideoLink("8880000000000000005", "DOM title no thumbnail")]) as unknown as Document,
  [{ aweme_id: "8880000000000000005", title: "Network no cover", raw_source: "network_json" }],
  [{ aweme_id: "8880000000000000005", title: "Detail no cover", raw_source: "detail_hydrate" }]
);
assert.equal(detailNoCoverVideos[0]?.thumbnail_url, null, "Placeholder must remain only when network, detail, and DOM all fail");
assert.equal(detailNoCoverVideos[0]?.thumbnail_source, "missing", "All-failed detail hydrate path must be marked missing");
assert.equal(detailNoCoverVideos[0]?.thumbnail_missing_reason, "detail_hydrate_no_cover", "Detail hydrate without cover must produce a precise missing reason");
assert.equal(detailNoCoverVideos[0]?.extraction_diagnostics?.thumbnail_missing_reason, "detail_hydrate_no_cover", "Missing reason must be available in diagnostics");

const noLeakVideos = extractVideos(
  new FakeDocument([
    makeVideoLink("8880000000000000006", "DOM title recovered", undefined),
    makeVideoLink("8880000000000000007", "DOM title still missing", undefined)
  ]) as unknown as Document,
  normalizeDouyinNetworkPayload({
    item_list: [
      {
        aweme_id: "8880000000000000006",
        desc: "Recovered item",
        video: { origin_cover: { url_list: ["https://p3.douyinpic.com/obj/recovered-8886.jpeg"] } },
        statistics: { play_count: 1 }
      }
    ]
  }, "network_cover_no_leak_fixture")
);
assert.deepEqual(noLeakVideos.map((video) => video.thumbnail_url), ["https://p3.douyinpic.com/obj/recovered-8886.jpeg", null], "Recovered thumbnail for one aweme_id must never leak to a neighboring missing aweme_id");
assert.deepEqual(noLeakVideos.map((video) => video.thumbnail_source), ["network_json", "missing"], "Thumbnail provenance must remain item-local across recovered and missing items");

const aliasOnlyNetworkItems = normalizeDouyinNetworkPayload({
  item_list: [
    {
      awemeId: "7420000000000000101",
      desc: "Alias-only awemeId must not become canonical network identity",
      video: { cover: { url_list: ["https://p3.douyinpic.com/obj/alias-only.jpeg"] } },
      statistics: { play_count: 777 }
    },
    {
      item_id: "7420000000000000102",
      desc: "Alias-only item_id must not become canonical network identity",
      video: { cover: { url_list: ["https://p3.douyinpic.com/obj/item-id-only.jpeg"] } },
      statistics: { play_count: 778 }
    },
    {
      id: "7420000000000000103",
      desc: "Alias-only id must not become canonical network identity",
      video: { cover: { url_list: ["https://p3.douyinpic.com/obj/id-only.jpeg"] } },
      statistics: { play_count: 779 }
    },
    {
      aweme_id: "7420000000000000104",
      desc: "Explicit aweme_id remains the only network identity",
      video: { cover: { url_list: ["https://p3.douyinpic.com/obj/explicit-aweme-id.jpeg"] } },
      statistics: { play_count: 780 }
    }
  ]
}, "identity_alias_fixture");
assert.deepEqual(aliasOnlyNetworkItems.map((item) => item.aweme_id), ["7420000000000000104"], "Network normalization must only admit records with an explicit aweme_id field");
const aliasOnlyVideos = extractVideos(fakeDocument, aliasOnlyNetworkItems);
assert.equal(aliasOnlyVideos[0]?.title?.includes("Alias-only"), false, "Network awemeId alias must not attach metadata to matching DOM aweme_id");
assert.equal(aliasOnlyVideos[1]?.title?.includes("Alias-only"), false, "Network item_id alias must not attach metadata by guessed identity");
assert.equal(aliasOnlyVideos[2]?.title?.includes("Alias-only"), false, "Network id alias must not attach metadata by guessed identity");
assert.equal(aliasOnlyVideos[3]?.raw?.network_aweme_id, "7420000000000000104", "Explicit aweme_id network record remains eligible for exact identity merge");

assert.notEqual(videos[0]?.url_list, videos[1]?.url_list, "Merged item url_list arrays must not reuse the same object reference across IDs");
assert.notEqual(videos[1]?.url_list, videos[2]?.url_list, "Merged item url_list arrays must not reuse the same object reference across IDs");
assert.notEqual(videos[2]?.url_list, videos[3]?.url_list, "Merged item url_list arrays must not reuse the same object reference across IDs");
assert.equal(videos[0]?.raw?.network_aweme_id, "7420000000000000101", "Raw diagnostics must expose the matched network aweme_id for the first item");
assert.equal(videos[1]?.raw?.network_aweme_id, "7420000000000000102", "Raw diagnostics must expose the matched network aweme_id for the second item");
assert.equal(videos[2]?.raw?.network_aweme_id, "7420000000000000103", "Raw diagnostics must expose the matched network aweme_id for the third item");
assert.equal(videos[3]?.raw?.network_aweme_id, "7420000000000000104", "Raw diagnostics must expose the matched network aweme_id for the DOM fallback item");

console.log("extension identity / aweme_id mapping tests passed");
