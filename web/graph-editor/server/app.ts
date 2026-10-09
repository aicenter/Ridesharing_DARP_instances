/**
 * The instance builder service: `POST /instances` runs the spec pipeline and renders the picture
 * in the editor that the service itself serves from `dist/`.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import JSZip from "jszip";
import type { InstanceFiles } from "../src/lib/exportInstance";
import type { ImportInstanceResult } from "../src/lib/importInstance";
import type { InstanceSpec } from "../src/lib/instanceSpec";
import {
  buildFromSpec,
  readSchema,
  type BuildFailure,
  type SpecValidator,
} from "../tools/instancePipeline";

/** Renders a state in the editor served at `editorUrl`; the service owns one for its lifetime. */
export type Renderer = {
  render(editorUrl: string, state: ImportInstanceResult, timeoutMs: number): Promise<Buffer>;
};

/** Upper bounds on a public request, so a render cannot run for minutes. */
export type SpecLimits = { nodes: number; edges: number; vehicles: number; requests: number };

export const DEFAULT_LIMITS: SpecLimits = { nodes: 200, edges: 2000, vehicles: 100, requests: 500 };

export const MAX_BODY_BYTES = 1024 * 1024;

export type AppOptions = {
  validate: SpecValidator;
  /** Built editor (`vite build` output) served at `/`. */
  distDir: string;
  /** `null`: pictures are not available (`png: null`, `pngError` set). */
  renderer: Renderer | null;
  limits?: SpecLimits;
  renderTimeoutMs?: number;
};

const STATIC_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".json": "application/json; charset=utf-8",
  ".woff2": "font/woff2",
};

class HttpError extends Error {
  readonly status: number;
  readonly failure: BuildFailure;

  constructor(status: number, failure: BuildFailure) {
    super(failure.errors.join("\n"));
    this.status = status;
    this.failure = failure;
  }
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(text),
    "access-control-allow-origin": "*",
  });
  res.end(text);
}

async function readJsonBody(req: IncomingMessage): Promise<unknown> {
  const declared = Number(req.headers["content-length"] ?? 0);
  if (declared > MAX_BODY_BYTES) {
    throw new HttpError(413, {
      ok: false,
      stage: "input",
      errors: [`request body exceeds ${MAX_BODY_BYTES} bytes.`],
    });
  }
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY_BYTES) {
      throw new HttpError(413, {
        ok: false,
        stage: "input",
        errors: [`request body exceeds ${MAX_BODY_BYTES} bytes.`],
      });
    }
    chunks.push(chunk as Buffer);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch (e) {
    throw new HttpError(400, {
      ok: false,
      stage: "input",
      errors: [`invalid JSON: ${e instanceof Error ? e.message : String(e)}`],
    });
  }
}

/** Element-count limits are checked on the raw spec before anything is built. */
function checkLimits(raw: unknown, limits: SpecLimits): string[] {
  if (typeof raw !== "object" || raw === null) return [];
  const spec = raw as Partial<InstanceSpec>;
  const errors: string[] = [];
  const check = (name: keyof SpecLimits, value: unknown, countEdges = false) => {
    if (!Array.isArray(value)) return;
    const count = countEdges
      ? value.reduce<number>((n, e) => n + ((e as { bidirectional?: boolean })?.bidirectional ? 2 : 1), 0)
      : value.length;
    if (count > limits[name]) errors.push(`${name}: ${count} exceed the limit of ${limits[name]}.`);
  };
  check("nodes", spec.nodes);
  check("edges", spec.edges, true);
  check("vehicles", spec.vehicles);
  check("requests", spec.requests);
  return errors;
}

async function zipOf(files: InstanceFiles, png: Buffer | null): Promise<Buffer> {
  const zip = new JSZip();
  for (const [name, text] of Object.entries(files)) zip.file(name, text);
  if (png) zip.file("instance.png", png);
  return zip.generateAsync({ type: "nodebuffer" });
}

/** Serializes the renders of a service: one page at a time. */
class RenderQueue {
  private tail: Promise<unknown> = Promise.resolve();

  run<T>(task: () => Promise<T>): Promise<T> {
    const next = this.tail.then(task, task);
    this.tail = next.catch(() => undefined);
    return next;
  }
}

export function createApp(opts: AppOptions): Server {
  const limits = opts.limits ?? DEFAULT_LIMITS;
  const renderTimeoutMs = opts.renderTimeoutMs ?? 30_000;
  const distDir = path.resolve(opts.distDir);
  const queue = new RenderQueue();
  let schemaText: string | null = null;

  async function serveStatic(pathname: string, res: ServerResponse): Promise<void> {
    const relative = pathname === "/" ? "index.html" : pathname.slice(1);
    const filePath = path.resolve(distDir, relative);
    if (!filePath.startsWith(distDir + path.sep)) return sendJson(res, 404, { error: "not found" });
    let info;
    try {
      info = await stat(filePath);
    } catch {
      return sendJson(res, 404, { error: "not found" });
    }
    if (!info.isFile()) return sendJson(res, 404, { error: "not found" });
    const type = STATIC_TYPES[path.extname(filePath)] ?? "application/octet-stream";
    const immutable = relative.startsWith("assets/");
    res.writeHead(200, {
      "content-type": type,
      "content-length": info.size,
      "cache-control": immutable ? "public, max-age=31536000, immutable" : "no-cache",
    });
    createReadStream(filePath).pipe(res);
  }

  async function buildInstance(req: IncomingMessage, res: ServerResponse, url: URL): Promise<void> {
    const raw = await readJsonBody(req);
    const limitErrors = checkLimits(raw, limits);
    if (limitErrors.length > 0) {
      throw new HttpError(400, { ok: false, stage: "limits", errors: limitErrors });
    }
    const built = buildFromSpec(raw, opts.validate);
    if (!built.ok) throw new HttpError(400, built);

    const wantPng = url.searchParams.get("png") !== "0";
    let png: Buffer | null = null;
    let pngError: string | null = null;
    if (wantPng) {
      if (!opts.renderer) {
        pngError = "This service renders no pictures.";
      } else {
        const editorUrl = `http://127.0.0.1:${(req.socket.localPort ?? 0).toString()}/`;
        try {
          png = await queue.run(() => opts.renderer!.render(editorUrl, built.state, renderTimeoutMs));
        } catch (e) {
          pngError = e instanceof Error ? e.message : String(e);
        }
      }
    }

    if ((req.headers.accept ?? "").includes("application/zip")) {
      const zip = await zipOf(built.files, png);
      res.writeHead(200, {
        "content-type": "application/zip",
        "content-length": zip.length,
        "content-disposition": 'attachment; filename="instance.zip"',
        "access-control-allow-origin": "*",
        ...(pngError !== null ? { "x-png-error": pngError } : {}),
      });
      res.end(zip);
      return;
    }
    sendJson(res, 200, {
      ok: pngError === null,
      files: built.files,
      png: png?.toString("base64") ?? null,
      ...(pngError !== null ? { pngError } : {}),
      counts: built.counts,
      warnings: built.warnings,
    });
  }

  async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const url = new URL(req.url ?? "/", "http://localhost");
    const method = req.method ?? "GET";

    if (method === "OPTIONS") {
      res.writeHead(204, {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "GET, POST, OPTIONS",
        "access-control-allow-headers": "content-type, accept",
        "access-control-max-age": "86400",
      });
      res.end();
      return;
    }
    if (url.pathname === "/instances") {
      if (method !== "POST") return sendJson(res, 405, { error: "use POST" });
      return buildInstance(req, res, url);
    }
    if (url.pathname === "/schema" && method === "GET") {
      schemaText ??= await readSchema();
      res.writeHead(200, {
        "content-type": "application/schema+json; charset=utf-8",
        "content-length": Buffer.byteLength(schemaText),
        "access-control-allow-origin": "*",
      });
      res.end(schemaText);
      return;
    }
    if (url.pathname === "/healthz" && method === "GET") return sendJson(res, 200, { ok: true });
    if (method === "GET" || method === "HEAD") return serveStatic(url.pathname, res);
    sendJson(res, 405, { error: "method not allowed" });
  }

  return createServer((req, res) => {
    handle(req, res).catch((e: unknown) => {
      if (e instanceof HttpError) return sendJson(res, e.status, e.failure);
      console.error(e instanceof Error ? (e.stack ?? e.message) : String(e));
      if (!res.headersSent) sendJson(res, 500, { error: "internal error" });
      else res.destroy();
    });
  });
}
