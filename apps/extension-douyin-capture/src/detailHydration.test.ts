import assert from "node:assert/strict";
import {
  extractExactDetailCandidates,
  hydrateDetailEvidenceForDiscoveries,
  hydrateOneDetailEvidence,
  runWithConcurrencyLimit
} from "./detailHydration";

{
  const html = `
    <html>
      <head>
        <script id="RENDER_DATA" type="application/json">
          {"data":{"aweme_detail":{"aweme_id":"8880000000000000001","create_time":1767225600,"desc":"Detail title","video":{"duration":42000},"statistics":{"play_count":888,"digg_count":1888,"comment_count":2888,"share_count":3888}}}}
        </script>
      </head>
    </html>
  `;
  const items = extractExactDetailCandidates(html, "text/html", "8880000000000000001");
  assert.equal(items.length, 1, "Detail hydration must extract one exact aweme item from embedded JSON");
  assert.equal(items[0]?.aweme_id, "8880000000000000001");
  assert.equal(items[0]?.duration_seconds, 42);
  assert.equal(items[0]?.view_count, 888);
  assert.equal(items[0]?.like_count, 1888);
  assert.equal(items[0]?.comment_count, 2888);
  assert.equal(items[0]?.share_count, 3888);
  assert.equal(items[0]?.raw_detail_aweme?.aweme_id, "8880000000000000001", "Detail evidence must preserve raw_detail_aweme");
}

{
  const json = JSON.stringify({
    outer: {
      nested: [
        {
          aweme_id: 7420123,
          create_time: 1767225600,
          video: { duration: 24000 },
          statistics: { play_count: 321, digg_count: 22 },
          author: { nickname: "fixture" }
        }
      ]
    }
  });
  const items = extractExactDetailCandidates(json, "application/json", "7420123");
  assert.equal(items.length, 1, "Recursive parser must find nested aweme detail by exact normalized aweme_id");
  assert.equal(items[0]?.aweme_id, "7420123");
}

{
  const json = JSON.stringify({
    data: {
      aweme_detail: {
        aweme_id: "9999999999999999999",
        create_time: 1767225600,
        video: { duration: 1000 },
        statistics: { play_count: 1 }
      }
    }
  });
  const items = extractExactDetailCandidates(json, "application/json", "8880000000000000001");
  assert.equal(items.length, 0, "Mismatched aweme_id must not attach detail evidence");
}

{
  const html = `
    <script type="application/json">
      {"data":{"aweme_detail":{"aweme_id":"8880000000000000002","create_time":1767225600,"video":{"duration":42000},"statistics":{"play_count":888},"cookie":"secret","token":"secret","author":{"nickname":"fixture"},"text_extra":[{"hashtag_name":"x"}],"music":{"title":"sound"}}}}
    </script>
  `;
  const item = extractExactDetailCandidates(html, "text/html", "8880000000000000002")[0];
  assert.ok(item?.raw_detail_aweme, "Detail raw aweme must exist");
  assert.equal("cookie" in (item?.raw_detail_aweme ?? {}), false, "Secret-like keys must be stripped from raw detail evidence");
  assert.equal("token" in (item?.raw_detail_aweme ?? {}), false, "Secret-like keys must be stripped from raw detail evidence");
  assert.equal(typeof item?.raw_detail_aweme?.video, "object", "Useful video object must remain in bounded raw detail evidence");
  assert.equal(typeof item?.raw_detail_aweme?.statistics, "object", "Useful statistics object must remain in bounded raw detail evidence");
}

{
  const responseBody = JSON.stringify({
    data: {
      aweme_detail: {
        aweme_id: "8880000000000000003",
        create_time: 1767225600,
        video: { duration: 5000 },
        statistics: { play_count: 55 }
      }
    }
  });
  const result = await hydrateOneDetailEvidence(
    { aweme_id: "8880000000000000003", source_url: "https://www.douyin.com/video/8880000000000000003" },
    {
      fetchImpl: async () => new Response(responseBody, { status: 200, headers: { "content-type": "application/json" } }),
      timeoutMs: 1000
    }
  );
  assert.equal(result?.raw_detail_aweme?.aweme_id, "8880000000000000003", "Hydration must fetch source_url and return exact raw_detail_aweme");
}

{
  const result = await hydrateDetailEvidenceForDiscoveries(
    [{ aweme_id: "8880000000000000004", source_url: "https://www.douyin.com/video/8880000000000000004" }],
    {
      fetchImpl: async () => {
        throw new DOMException("Timeout", "AbortError");
      },
      timeoutMs: 10
    }
  );
  assert.equal(result.items.length, 0, "Timeout must not fabricate detail evidence");
  assert.equal(result.stats.detail_hydrate_attempted_count, 1, "Timeout still counts as an attempted detail hydrate");
  assert.equal(result.stats.detail_hydrate_timeout_count, 1, "Timeout must be tracked separately");
}

{
  let active = 0;
  let maxActive = 0;
  const results = await runWithConcurrencyLimit(
    Array.from({ length: 5 }, (_, index) => async () => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((resolve) => setTimeout(resolve, 5));
      active -= 1;
      return index;
    }),
    2
  );
  assert.deepEqual(results, [0, 1, 2, 3, 4], "Concurrency helper must preserve task result ordering");
  assert.equal(maxActive <= 2, true, "Concurrency helper must respect the configured limit");
}

{
  const result = await hydrateDetailEvidenceForDiscoveries(
    [
      { aweme_id: "8880000000000000005", source_url: "https://www.douyin.com/video/8880000000000000005" },
      { aweme_id: "8880000000000000006", source_url: "https://www.douyin.com/video/8880000000000000006" }
    ],
    {
      fetchImpl: async (input) => {
        const url = String(input);
        const id = url.split("/video/")[1];
        return new Response(
          JSON.stringify({
            data: {
              aweme_detail: {
                aweme_id: id,
                create_time: 1767225600,
                video: { duration: 7000 },
                statistics: { play_count: 77, digg_count: 17 }
              }
            }
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
    }
  );
  assert.equal(result.stats.detail_hydrate_success_count, 2, "Successful detail hydrates must be counted");
  assert.equal(result.stats.raw_detail_aweme_attached_count, 2, "Attached raw detail evidence count must track exact attached items");
}

{
  const encoded = encodeURIComponent(JSON.stringify({
    data: {
      aweme_detail: {
        aweme_id: "8880000000000000007",
        create_time: 1767225600,
        desc: "Encoded render data",
        video: { duration: 33000, cover: { url_list: ["https://p3-sign.douyinpic.com/tos-cn-i/enc~tplv.jpeg?x-signature=sig"] } },
        statistics: { digg_count: 99, comment_count: 8, collect_count: 4, share_count: 2 }
      }
    }
  }));
  const html = `<script id="RENDER_DATA" type="application/json">${encoded}</script>`;
  const items = extractExactDetailCandidates(html, "text/html", "8880000000000000007");
  assert.equal(items.length, 1, "URL-encoded RENDER_DATA must parse");
  assert.equal(items[0]?.duration_seconds, 33);
  assert.equal(items[0]?.favorite_count, 4);
}

{
  const apiBody = JSON.stringify({
    aweme_detail: {
      aweme_id: "8880000000000000008",
      create_time: 1767225600,
      video: { duration: 12000, cover: { url_list: ["https://p3-sign.douyinpic.com/tos-cn-i/api~tplv.jpeg?x-signature=sig"] } },
      statistics: { digg_count: 12, comment_count: 3, collect_count: 1, share_count: 0 }
    }
  });
  const result = await hydrateOneDetailEvidence(
    { aweme_id: "8880000000000000008", source_url: "https://www.douyin.com/video/8880000000000000008" },
    {
      fetchImpl: async (input) => {
        const url = String(input);
        if (url.includes("/aweme/v1/web/aweme/detail/")) {
          return new Response(apiBody, { status: 200, headers: { "content-type": "application/json" } });
        }
        return new Response("<html></html>", { status: 200, headers: { "content-type": "text/html" } });
      },
      timeoutMs: 1000
    }
  );
  assert.ok(result, "aweme detail API fallback must hydrate when video page is empty");
  assert.equal(result?.aweme_id, "8880000000000000008");
  assert.equal(result?.like_count, 12);
}

console.log("extension detail hydration tests passed");
