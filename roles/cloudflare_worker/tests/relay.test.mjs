import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import worker from "../files/relay.mjs";

const env = {
  ROUTES: JSON.stringify({
    "api.telegram.org": ["/bot111:", "/file/bot111:"],
    "api.example.org": ["/v1/"],
    "files.example.org": ["/"],
  }),
};
let forwarded;

beforeEach(() => {
  forwarded = [];
  globalThis.fetch = async (request) => {
    forwarded.push(request);
    return new Response("from upstream");
  };
});

const call = (path, init) => worker.fetch(new Request(`https://relay.example${path}`, init), env);

test("a call goes to the upstream with its method, query, headers and body", async () => {
  const response = await call("/api.telegram.org/bot111:secret/sendMessage?x=1", {
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

test("a bot under its prefixes downloads files and long-polls with GET", async () => {
  await call("/api.telegram.org/file/bot111:secret/photos/a.jpg");
  await call("/api.telegram.org/bot111:secret/getUpdates?timeout=50");
  assert.deepEqual(forwarded.map((r) => [r.method, r.url]), [
    ["GET", "https://api.telegram.org/file/bot111:secret/photos/a.jpg"],
    ["GET", "https://api.telegram.org/bot111:secret/getUpdates?timeout=50"],
  ]);
});

for (const path of ["/bot222:secret/getMe", "/bot1111:secret/getMe", "/x/bot111:secret/getMe", "/bot111/getMe", ""]) {
  test(`api.telegram.org${path} is not relayed for bot 111 alone`, async () => {
    const response = await call(`/api.telegram.org${path}`, { method: "POST" });
    assert.equal(response.status, 404);
    assert.equal(forwarded.length, 0);
  });
}

test("the first segment picks the upstream and the rest goes to it", async () => {
  await call("/api.example.org/v1/items?id=2", { method: "PUT", body: "x" });
  await call("/files.example.org/a/b.txt");
  await call("/files.example.org");
  assert.deepEqual(forwarded.map((r) => [r.method, r.url]), [
    ["PUT", "https://api.example.org/v1/items?id=2"],
    ["GET", "https://files.example.org/a/b.txt"],
    ["GET", "https://files.example.org/"],
  ]);
});

for (const path of [
  "/",
  "/api.example.org",
  "/api.example.org/v1",
  "/api.example.org/v2/items",
  "/api.example.org/v1/../admin",
  "/api.example.org/../evil.example/v1/",
  "/evil.example/v1/",
  "/api.example.org@evil.example/v1/",
  "/api.example.org:8443/v1/",
  "/hasOwnProperty/",
]) {
  test(`${path} is not relayed`, async () => {
    const response = await call(path);
    assert.equal(response.status, 404);
    assert.equal(forwarded.length, 0);
  });
}
