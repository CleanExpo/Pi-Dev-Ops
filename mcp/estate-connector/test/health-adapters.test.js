import assert from "node:assert/strict";
import path from "node:path";
import { test } from "node:test";
import { ato } from "../adapters/ato/index.js";
import { carsi } from "../adapters/carsi/index.js";
import { drnrpg } from "../adapters/drnrpg/index.js";
import { restoreassist } from "../adapters/restoreassist/index.js";
import { synthex } from "../adapters/synthex/index.js";

const REPO_ROOT = path.resolve(import.meta.dirname, "../../..");

function toolOf(adapter, name) {
  const tool = adapter.tools().find((item) => item.name === name);
  assert.ok(tool, name);
  return tool;
}

function bodyOf(result) {
  return JSON.parse(result.content[0].text);
}

async function withFetch(impl, run) {
  const original = globalThis.fetch;
  globalThis.fetch = impl;
  try {
    return await run();
  } finally {
    globalThis.fetch = original;
  }
}

test("restoreassist_health uses the default site and returns JSON", async () => {
  const tool = toolOf(restoreassist, "restoreassist_health");
  await withFetch(async (url, init) => {
    assert.equal(url, "https://restoreassist.app/api/health");
    assert.equal(init.headers.authorization, undefined);
    return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
  }, async () => {
    const result = await tool.handler({}, { repoRoot: REPO_ROOT, env: {} });
    const body = bodyOf(result);
    assert.equal(body.ok, true);
    assert.equal(body.status, 200);
    assert.equal(body.body.status, "ok");
    assert.equal(body.registry.repo, "CleanExpo/RestoreAssist");
    assert.equal(Boolean(result.isError), false);
  });
});

test("synthex_health uses the env base and reports a non-200", async () => {
  const tool = toolOf(synthex, "synthex_health");
  await withFetch(async (url, init) => {
    assert.equal(url, "http://127.0.0.1:9/api/health");
    assert.equal(init.headers.authorization, "Bearer site-token");
    return new Response(JSON.stringify({ status: "unhealthy" }), { status: 503 });
  }, async () => {
    const result = await tool.handler({}, {
      repoRoot: REPO_ROOT,
      env: { SYNTHEX_BASE_URL: "http://127.0.0.1:9", SYNTHEX_BEARER_TOKEN: "site-token" },
    });
    const body = bodyOf(result);
    assert.equal(body.ok, false);
    assert.equal(body.status, 503);
    assert.equal(body.body.status, "unhealthy");
    assert.equal(body.registry.id, "synthex");
    assert.equal(Boolean(result.isError), false);
  });
});

test("ato_health uses the default site when the base URL is blank", async () => {
  const tool = toolOf(ato, "ato_health");
  await withFetch(async (url, init) => {
    assert.equal(url, "https://ato-ai.app/api/health");
    assert.equal(init.headers.authorization, undefined);
    return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
  }, async () => {
    const result = await tool.handler({}, {
      repoRoot: REPO_ROOT,
      env: { ATO_BASE_URL: "", ATO_BEARER_TOKEN: "" },
    });
    const body = bodyOf(result);
    assert.equal(body.ok, true);
    assert.equal(body.status, 200);
    assert.equal(body.body.status, "ok");
    assert.equal(body.registry.id, "ato");
    assert.equal(body.registry.repo, "CleanExpo/ATO");
    assert.equal(Boolean(result.isError), false);
  });
});

test("carsi_health uses the default site and returns JSON", async () => {
  const tool = toolOf(carsi, "carsi_health");
  await withFetch(async (url, init) => {
    assert.equal(url, "https://carsi.com.au/api/health");
    assert.equal(init.headers.authorization, undefined);
    return new Response(JSON.stringify({ status: "healthy" }), { status: 200 });
  }, async () => {
    const result = await tool.handler({}, { repoRoot: REPO_ROOT, env: {} });
    const body = bodyOf(result);
    assert.equal(body.ok, true);
    assert.equal(body.status, 200);
    assert.equal(body.body.status, "healthy");
    assert.equal(body.registry.id, "carsi");
    assert.equal(body.registry.repo, "CleanExpo/carsi");
    assert.equal(Boolean(result.isError), false);
  });
});

test("carsi_health uses the env base and reports a non-200", async () => {
  const tool = toolOf(carsi, "carsi_health");
  await withFetch(async (url, init) => {
    assert.equal(url, "http://127.0.0.1:9/api/health");
    assert.equal(init.headers.authorization, "Bearer site-token");
    return new Response(JSON.stringify({ status: "unhealthy" }), { status: 503 });
  }, async () => {
    const result = await tool.handler({}, {
      repoRoot: REPO_ROOT,
      env: { CARSI_BASE_URL: "http://127.0.0.1:9", CARSI_BEARER_TOKEN: "site-token" },
    });
    const body = bodyOf(result);
    assert.equal(body.ok, false);
    assert.equal(body.status, 503);
    assert.equal(body.body.status, "unhealthy");
    assert.equal(body.registry.id, "carsi");
    assert.equal(Boolean(result.isError), false);
  });
});

test("drnrpg_health keeps a non-JSON body", async () => {
  const tool = toolOf(drnrpg, "drnrpg_health");
  await withFetch(async (url) => {
    assert.equal(url, "https://dr-nrpg-platform.vercel.app/api/health");
    return new Response("upstream down", { status: 502, headers: { "content-type": "text/plain" } });
  }, async () => {
    const result = await tool.handler({}, { repoRoot: REPO_ROOT, env: {} });
    const body = bodyOf(result);
    assert.equal(body.ok, false);
    assert.equal(body.status, 502);
    assert.equal(body.body.raw, "upstream down");
    assert.equal(body.registry.id, "dr-nrpg");
    assert.equal(Boolean(result.isError), false);
  });
});
