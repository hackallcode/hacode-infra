import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import worker from "../files/worker.mjs";

const env = { BOT_IDS: JSON.stringify(["111"]) };
let forwarded;

beforeEach(() => {
  forwarded = [];
  globalThis.fetch = async (request) => {
    forwarded.push(request);
    return new Response("from telegram");
  };
});

const call = (path, init) => worker.fetch(new Request(`https://relay.example${path}`, init), env);

test("a listed bot's call goes to api.telegram.org as it came", async () => {
  const response = await call("/bot111:secret/sendMessage?x=1", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: '{"chat_id":1}',
  });
  assert.equal(await response.text(), "from telegram");
  assert.equal(forwarded.length, 1);
  assert.equal(forwarded[0].url, "https://api.telegram.org/bot111:secret/sendMessage?x=1");
  assert.equal(forwarded[0].method, "POST");
  assert.equal(forwarded[0].headers.get("content-type"), "application/json");
  assert.equal(await forwarded[0].text(), '{"chat_id":1}');
});

test("a listed bot downloads its files and long-polls with GET", async () => {
  await call("/file/bot111:secret/photos/a.jpg");
  await call("/bot111:secret/getUpdates?timeout=50");
  assert.deepEqual(forwarded.map((r) => [r.method, r.url]), [
    ["GET", "https://api.telegram.org/file/bot111:secret/photos/a.jpg"],
    ["GET", "https://api.telegram.org/bot111:secret/getUpdates?timeout=50"],
  ]);
});

for (const path of ["/bot222:secret/getMe", "/bot1111:secret/getMe", "/x/bot111:secret/getMe", "/bot111/getMe", "/"]) {
  test(`${path} is not relayed`, async () => {
    const response = await call(path, { method: "POST" });
    assert.equal(response.status, 404);
    assert.equal(forwarded.length, 0);
  });
}
