/**
 * Headless instance builder: turns an instance spec (`JSON/instance_spec.schema.json`) into the
 * instance files and a picture of the instance, using the graph editor code.
 *
 *   npm run build-instance -- <spec.json> --out <dir> [--no-png] [--zip] [--url <editor url>]
 *                                                     [--service <builder service url>]
 *                                                     [--timeout <ms>] [--viewport <w>x<h>]
 *
 * With `--service`, the spec is built by the hosted builder service instead of locally (no
 * browser needed). Prints one JSON summary to stdout. Exit codes: 0 ok, 1 invalid spec or files
 * not written, 2 files written but no picture.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import JSZip from "jszip";
import type { InstanceFiles } from "../src/lib/exportInstance";
import { DEFAULT_VIEWPORT, EditorRenderer, type Viewport } from "./editorRenderer";
import {
  buildFromSpec,
  loadSpecValidator,
  type BuildFailure,
  type ElementCounts,
} from "./instancePipeline";

const EDITOR_ROOT = fileURLToPath(new URL("..", import.meta.url));
const PNG_NAME = "instance.png";
const ZIP_NAME = "instance.zip";

type Options = {
  specPath: string;
  outDir: string;
  png: boolean;
  zip: boolean;
  url: string | null;
  service: string | null;
  timeoutMs: number;
  viewport: Viewport;
};

class UsageError extends Error {}

function parseOptions(argv: string[]): Options {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: {
      out: { type: "string", short: "o" },
      "no-png": { type: "boolean", default: false },
      zip: { type: "boolean", default: false },
      url: { type: "string" },
      service: { type: "string" },
      timeout: { type: "string", default: "60000" },
      viewport: { type: "string", default: `${DEFAULT_VIEWPORT.width}x${DEFAULT_VIEWPORT.height}` },
    },
  });
  if (positionals.length !== 1) throw new UsageError("Expected exactly one spec file.");
  if (!values.out) throw new UsageError("Missing --out <dir>.");
  if (values.service && values.url) throw new UsageError("--service and --url exclude each other.");
  const timeoutMs = Number(values.timeout);
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0) {
    throw new UsageError(`Invalid --timeout: ${values.timeout}`);
  }
  const vp = /^(\d+)x(\d+)$/.exec(values.viewport);
  if (!vp) throw new UsageError(`Invalid --viewport: ${values.viewport} (expected <w>x<h>)`);
  return {
    specPath: path.resolve(positionals[0]),
    outDir: path.resolve(values.out),
    png: !values["no-png"],
    zip: values.zip,
    url: values.url ?? null,
    service: values.service ?? null,
    timeoutMs,
    viewport: { width: Number(vp[1]), height: Number(vp[2]) },
  };
}

function fail(failure: BuildFailure): never {
  console.log(JSON.stringify(failure, null, 2));
  process.exit(1);
}

/** What the builder produces before anything is written. */
type Built = {
  files: InstanceFiles;
  png: Buffer | null;
  pngError: string | null;
  counts: ElementCounts;
  warnings: string[];
};

/** Builds the spec locally: pipeline in this process, picture in a headless browser. */
async function buildLocally(raw: unknown, opts: Options): Promise<Built> {
  const built = buildFromSpec(raw, await loadSpecValidator());
  if (!built.ok) fail(built);

  let png: Buffer | null = null;
  let pngError: string | null = null;
  if (opts.png) {
    try {
      png = await renderPng(built.state, opts);
    } catch (e) {
      pngError = e instanceof Error ? e.message : String(e);
    }
  }
  return { files: built.files, png, pngError, counts: built.counts, warnings: built.warnings };
}

async function renderPng(state: Parameters<EditorRenderer["render"]>[1], opts: Options): Promise<Buffer> {
  const { createServer } = await import("vite");
  const server = opts.url
    ? null
    : await createServer({
        root: EDITOR_ROOT,
        configFile: path.join(EDITOR_ROOT, "vite.config.ts"),
        server: { host: "127.0.0.1", hmr: false, open: false },
        logLevel: "silent",
      });
  let renderer: EditorRenderer | null = null;
  try {
    let editorUrl = opts.url;
    if (server) {
      await server.listen();
      editorUrl = server.resolvedUrls?.local[0] ?? null;
      if (!editorUrl) throw new Error("The Vite dev server did not report a URL.");
    }
    renderer = await EditorRenderer.launch({
      chromiumPath: process.env.DARP_CHROMIUM_PATH,
      viewport: opts.viewport,
    });
    return await renderer.render(editorUrl!, state, opts.timeoutMs);
  } finally {
    await renderer?.close();
    await server?.close();
  }
}

/** Response of the builder service's `POST /instances`. */
type ServiceResponse =
  | BuildFailure
  | {
      ok: boolean;
      files: InstanceFiles;
      png: string | null;
      pngError?: string;
      counts: ElementCounts;
      warnings: string[];
    };

/** Builds the spec through the hosted builder service. */
async function buildRemotely(raw: unknown, opts: Options): Promise<Built> {
  const url = new URL("instances", opts.service!.endsWith("/") ? opts.service! : `${opts.service}/`);
  if (!opts.png) url.searchParams.set("png", "0");
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify(raw),
    signal: AbortSignal.timeout(opts.timeoutMs),
  });
  const body = (await response.json()) as ServiceResponse;
  if (!("files" in body)) {
    if (response.ok) throw new Error(`Unexpected response from ${url}: ${JSON.stringify(body)}`);
    fail(body);
  }
  return {
    files: body.files,
    png: body.png === null ? null : Buffer.from(body.png, "base64"),
    pngError: body.pngError ?? null,
    counts: body.counts,
    warnings: body.warnings,
  };
}

async function writeZip(outDir: string, files: InstanceFiles, png: Buffer | null): Promise<string> {
  const zip = new JSZip();
  for (const [name, text] of Object.entries(files)) zip.file(name, text);
  if (png) zip.file(PNG_NAME, png);
  const zipPath = path.join(outDir, ZIP_NAME);
  await writeFile(zipPath, await zip.generateAsync({ type: "nodebuffer" }));
  return zipPath;
}

async function main(argv: string[]): Promise<number> {
  const opts = parseOptions(argv);

  let raw: unknown;
  try {
    raw = JSON.parse(await readFile(opts.specPath, "utf8"));
  } catch (e) {
    fail({
      ok: false,
      stage: "input",
      errors: [`${opts.specPath}: ${e instanceof Error ? e.message : String(e)}`],
    });
  }

  const built = opts.service ? await buildRemotely(raw, opts) : await buildLocally(raw, opts);

  await mkdir(opts.outDir, { recursive: true });
  const written: Record<string, string> = {};
  for (const [name, text] of Object.entries(built.files)) {
    const filePath = path.join(opts.outDir, name);
    await writeFile(filePath, text);
    written[name] = filePath;
  }
  if (built.png) {
    const pngPath = path.join(opts.outDir, PNG_NAME);
    await writeFile(pngPath, built.png);
    written[PNG_NAME] = pngPath;
  }
  if (opts.zip) written[ZIP_NAME] = await writeZip(opts.outDir, built.files, built.png);

  const summary = {
    ok: built.pngError === null,
    outDir: opts.outDir,
    files: written,
    png: written[PNG_NAME] ?? null,
    ...(built.pngError !== null ? { pngError: built.pngError } : {}),
    counts: built.counts,
    warnings: built.warnings,
  };
  console.log(JSON.stringify(summary, null, 2));
  return built.pngError === null ? 0 : 2;
}

main(process.argv.slice(2)).then(
  (code) => process.exit(code),
  (e) => {
    if (e instanceof UsageError) {
      console.error(`build-instance: ${e.message}`);
      console.error(
        "usage: build-instance <spec.json> --out <dir> [--no-png] [--zip] [--url <editor url>] [--service <url>] [--timeout <ms>] [--viewport <w>x<h>]",
      );
    } else {
      console.error(e instanceof Error ? (e.stack ?? e.message) : String(e));
    }
    process.exit(1);
  },
);
