import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import worker from "../files/relay.mjs";

// The paths the role builds in telegram mode for bot 111.
const telegram = { UPSTREAM: "https://api.telegram.org", PATHS: JSON.stringify(["/bot111:", "/file/bot111:"]) };
const api = { UPSTREAM: "https://api.example.org", PATHS: JSON.stringify(["/v1/"]) };
let forwarded;

beforeEach(() => {
  forwarded = [];
  globalThis.fetch = async (request) => {
    forwarded.push(request);
    return new Response("from upstream");
  };
});

const call = (env, path, init) => worker.fetch(new Request(`https://relay.example${path}`, init), env);

test("a listed bot's call goes to api.telegram.org as it came", async () => {
  const response = await call(telegram, "/bot111:secret/sendMessage?x=1", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: '{"chat_id":1}',
  });
  assert.equal(await response.text(), "from upstream");
  assert.equal(forwarded.length, 1);
  assert.equal(forwarded[0].url, "https://api.telegram.org/bot111:secret/sendMessage?x=1");
  assert.equal(forwarded[0].method, "POST");
  assert.equal(forwarded[0].headers.get("content-type"), "application/json");
  assert.equal(await forwarded[0].text(), '{"chat_id":1}');
});

test("a listed bot downloads its files and long-polls with GET", async () => {
  await call(telegram, "/file/bot111:secret/photos/a.jpg");
  await call(telegram, "/bot111:secret/getUpdates?timeout=50");
  assert.deepEqual(forwarded.map((r) => [r.method, r.url]), [
    ["GET", "https://api.telegram.org/file/bot111:secret/photos/a.jpg"],
    ["GET", "https://api.telegram.org/bot111:secret/getUpdates?timeout=50"],
  ]);
});

for (const path of ["/bot222:secret/getMe", "/bot1111:secret/getMe", "/x/bot111:secret/getMe", "/bot111/getMe", "/"]) {
  test(`${path} is not relayed for bot 111`, async () => {
    const response = await call(telegram, path, { method: "POST" });
    assert.equal(response.status, 404);
    assert.equal(forwarded.length, 0);
  });
}

test("a path under a listed prefix goes to the upstream", async () => {
  await call(api, "/v1/items?id=2");
  assert.deepEqual(forwarded.map((r) => r.url), ["https://api.example.org/v1/items?id=2"]);
});

for (const path of ["/v1", "/v2/items", "/v1/../admin"]) {
  test(`${path} is not relayed outside /v1/`, async () => {
    const response = await call(api, path);
    assert.equal(response.status, 404);
    assert.equal(forwarded.length, 0);
  });
}
