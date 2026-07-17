import assert from "node:assert/strict";
import { normalizeDouyinNetworkPayload } from "./networkCache";

{
  const items = normalizeDouyinNetworkPayload({
    data: {
      list: [
        {
          aweme_id: 7420123,
          desc: "Nested recursive record",
          create_time: 1767225600,
          video: {
            duration: 24000,
            cover: { url_list: ["//p3.douyinpic.com/obj/nested-cover.webp"] }
          },
          statistics: {
            play_count: "12345",
            digg_count: 456,
            comment_count: "78",
            share_count: 9
          },
          author: { nickname: "fixture" }
        }
      ]
    }
  }, "api/detail/hydrate");

  assert.equal(items.length, 1, "Recursive nested payload detection must find one aweme record");
  assert.equal(items[0]?.aweme_id, "7420123", "Numeric aweme_id must normalize to a trimmed string");
  assert.equal(items[0]?.duration_seconds, 24, "Video duration must normalize from milliseconds");
  assert.equal(items[0]?.view_count, 12345, "play_count must map into canonical view_count");
  assert.equal(items[0]?.like_count, 456, "digg_count must map into canonical like_count");
  assert.equal(items[0]?.comment_count, 78, "comment_count must map into canonical comment_count");
  assert.equal(items[0]?.share_count, 9, "share_count must map into canonical share_count");
  assert.equal(items[0]?.raw_detail_aweme?.aweme_id, 7420123, "Detail-source payload must preserve bounded raw aweme evidence");
  assert.equal(typeof items[0]?.raw_detail_aweme?.video, "object", "Bounded raw aweme evidence must keep the video object");
  assert.equal(typeof items[0]?.raw_detail_aweme?.statistics, "object", "Bounded raw aweme evidence must keep the statistics object");
  assert.equal(items[0]?.raw_network_aweme ?? null, null, "Detail-source payload must not fake network evidence");
}

{
  const items = normalizeDouyinNetworkPayload({
    aweme_list: [
      {
        aweme_id: "7420000000000000456",
        desc: "Shallow list record",
        create_time: 1767225601,
        video: { duration: 11000 },
        statistics: { play_count: 456, digg_count: 45 }
      }
    ]
  }, "api/feed/list");

  assert.equal(items.length, 1, "Shallow aweme_list detection must still work");
  assert.equal(items[0]?.raw_network_aweme?.aweme_id, "7420000000000000456", "Network-source payload must preserve raw network aweme evidence");
  assert.equal(items[0]?.raw_detail_aweme ?? null, null, "Network-source payload must not fake detail evidence");
}

console.log("extension network cache tests passed");
