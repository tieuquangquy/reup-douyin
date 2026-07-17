import assert from "node:assert/strict";
import {
  OPERATOR_LIST_PAGE_SIZE_PRESETS,
  readOperatorListPageSize,
  resolveOperatorListPageSize,
  writeOperatorListPageSize,
} from "../lib/operatorListPageSize";

assert.deepEqual(OPERATOR_LIST_PAGE_SIZE_PRESETS, [25, 50, 100]);

assert.equal(resolveOperatorListPageSize(null, OPERATOR_LIST_PAGE_SIZE_PRESETS, 50), 50);
assert.equal(resolveOperatorListPageSize("50", OPERATOR_LIST_PAGE_SIZE_PRESETS, 50), 50);
assert.equal(resolveOperatorListPageSize("25", OPERATOR_LIST_PAGE_SIZE_PRESETS, 50), 25);
assert.equal(resolveOperatorListPageSize("100", OPERATOR_LIST_PAGE_SIZE_PRESETS, 50), 100);
assert.equal(resolveOperatorListPageSize("200", OPERATOR_LIST_PAGE_SIZE_PRESETS, 50), 50, "values outside presets fall back to default");
assert.equal(resolveOperatorListPageSize("nope", OPERATOR_LIST_PAGE_SIZE_PRESETS, 50), 50);
assert.equal(resolveOperatorListPageSize("0", OPERATOR_LIST_PAGE_SIZE_PRESETS, 50), 50);

const memory = new Map<string, string>();
const storage = {
  getItem: (key: string) => memory.get(key) ?? null,
  setItem: (key: string, value: string) => {
    memory.set(key, value);
  },
};

assert.equal(readOperatorListPageSize("reup.queue.pageSize", OPERATOR_LIST_PAGE_SIZE_PRESETS, 50, storage), 50);
writeOperatorListPageSize("reup.queue.pageSize", 100, OPERATOR_LIST_PAGE_SIZE_PRESETS, storage);
assert.equal(memory.get("reup.queue.pageSize"), "100");
assert.equal(readOperatorListPageSize("reup.queue.pageSize", OPERATOR_LIST_PAGE_SIZE_PRESETS, 50, storage), 100);
writeOperatorListPageSize("ops.jobs.pageSize", 200, OPERATOR_LIST_PAGE_SIZE_PRESETS, storage);
assert.equal(memory.has("ops.jobs.pageSize"), false, "invalid page size must not persist");

console.log("operatorListPageSize.test.ts: ok");
