import { existsSync, readFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { fileURLToPath } from "node:url";
import JSZip from "jszip";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { loadSpecValidator } from "../tools/instancePipeline";
import { createApp, MAX_BODY_BYTES, type Renderer } from "./app";

const DIST_DIR = fileURLToPath(new URL("../dist", import.meta.url));
const PNG_STUB = Buffer.from([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);

function example(name: string): unknown {
  return JSON.parse(readFileSync(new URL(`../examples/${name}`, import.meta.url), "utf8"));
}

/** Records the editor URL it was asked to render at. */
const renderer: Renderer & { urls: string[]; fail: boolean } = {
  urls: [],
  fail: false,
  async render(editorUrl) {
    this.urls.push(editorUrl);
    if (this.fail) throw new Error("boom");
    return PNG_STUB;
  },
};

const server = createApp({
  validate: await loadSpecValidator(),
  distDir: DIST_DIR,
  renderer,
  limits: { nodes: 10, edges: 20, vehicles: 5, requests: 5 },
});
let base = "";

beforeAll(async () => {
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
afterAll(() => new Promise<void>((resolve) => server.close(() => resolve())));

function post(body: unknown, init: RequestInit = {}, query = ""): Promise<Response> {
  return fetch(`${base}/instances${query}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
    body: typeof body === "string" ? body : JSON.stringify(body),
    ...init,
  });
}

describe("POST /instances", () => {
  it("builds the files and the picture", async () => {
    const res = await post(example("small-darp.json"));
    expect(res.status).toBe(200);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
    const body = (await res.json()) as {
      ok: boolean;
      files: Record<string, string>;
      png: string;
      counts: Record<string, number>;
      warnings: string[];
    };
    expect(body.ok).toBe(true);
    expect(Object.keys(body.files).sort()).toEqual(
      ["config.yaml", "dm.csv", "requests.csv", "vehicle_data.json", "vehicles.csv"],
    );
    expect(Buffer.from(body.png, "base64")).toEqual(PNG_STUB);
    expect(body.counts).toEqual({ nodes: 4, edges: 7, vehicles: 2, requests: 3 });
    expect(body.warnings).toEqual([]);
    // The picture is rendered in the editor the service serves itself.
    expect(renderer.urls.at(-1)).toBe(`${base}/`);
  });

  it("skips the picture with ?png=0", async () => {
    const before = renderer.urls.length;
    const body = (await (await post(example("small-darp.json"), {}, "?png=0")).json()) as {
      ok: boolean;
      png: string | null;
    };
    expect(body).toMatchObject({ ok: true, png: null });
    expect(renderer.urls.length).toBe(before);
  });

  it("returns a zip on Accept: application/zip", async () => {
    const res = await post(example("fleet-sizing-no-positions.json"), {
      headers: { accept: "application/zip" },
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/zip");
    const zip = await JSZip.loadAsync(Buffer.from(await res.arrayBuffer()));
    expect(Object.keys(zip.files).sort()).toEqual(
      ["config.yaml", "dm.csv", "instance.png", "requests.csv"],
    );
  });

  it("still returns the files when the picture fails", async () => {
    renderer.fail = true;
    try {
      const res = await post(example("small-darp.json"));
      expect(res.status).toBe(200);
      const body = (await res.json()) as { ok: boolean; png: string | null; pngError: string };
      expect(body).toMatchObject({ ok: false, png: null, pngError: "boom" });
    } finally {
      renderer.fail = false;
    }
  });

  it("rejects a spec violating the schema", async () => {
    const res = await post({ nodes: [{ id: 0 }], edges: [], vehicles: [{ position: 0, capacity: "4" }] });
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({
      ok: false,
      stage: "schema",
      errors: ["/vehicles/0/capacity: must be integer"],
    });
  });

  it("rejects a semantically invalid spec", async () => {
    const res = await post({ nodes: [{ id: 0 }, { id: 1 }], edges: [{ from: 0, to: 9, travel_time: 1 }] });
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ ok: false, stage: "semantic" });
  });

  it("rejects a spec above the element limits before building it", async () => {
    const nodes = Array.from({ length: 11 }, (_, id) => ({ id }));
    const res = await post({ nodes, edges: [] });
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({
      ok: false,
      stage: "limits",
      errors: ["nodes: 11 exceed the limit of 10."],
    });
  });

  it("rejects invalid JSON and oversized bodies", async () => {
    expect((await post("{nodes:")).status).toBe(400);
    const big = JSON.stringify({ nodes: [], edges: [], pad: "x".repeat(MAX_BODY_BYTES) });
    expect((await post(big)).status).toBe(413);
  });

  it("answers CORS preflight and rejects GET", async () => {
    const preflight = await fetch(`${base}/instances`, { method: "OPTIONS" });
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get("access-control-allow-methods")).toContain("POST");
    expect((await fetch(`${base}/instances`)).status).toBe(405);
  });
});

describe("other routes", () => {
  it("serves the schema and the health check", async () => {
    const schema = await fetch(`${base}/schema`);
    expect(schema.status).toBe(200);
    expect(((await schema.json()) as { $id: string }).$id).toBe("instance_spec.schema.json");
    expect(await (await fetch(`${base}/healthz`)).json()).toEqual({ ok: true });
  });

  it.skipIf(!existsSync(`${DIST_DIR}/index.html`))("serves the built editor", async () => {
    const page = await fetch(`${base}/`);
    expect(page.status).toBe(200);
    expect(page.headers.get("content-type")).toContain("text/html");
    expect(await page.text()).toContain('<div id="root">');
    expect((await fetch(`${base}/favicon.svg`)).headers.get("content-type")).toBe("image/svg+xml");
  });

  it("does not leave the dist directory", async () => {
    expect((await fetch(`${base}/../package.json`)).status).toBe(404);
    expect((await fetch(`${base}/%2e%2e/package.json`)).status).toBe(404);
    expect((await fetch(`${base}/nope.js`)).status).toBe(404);
  });
});
