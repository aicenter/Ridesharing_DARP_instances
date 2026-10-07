/**
 * Headless instance builder: turns an instance spec (`JSON/instance_spec.schema.json`) into the
 * instance files and a picture of the instance, using the graph editor code.
 *
 *   npm run build-instance -- <spec.json> --out <dir> [--no-png] [--zip] [--url <editor url>]
 *                                                     [--timeout <ms>] [--viewport <w>x<h>]
 *
 * Prints one JSON summary to stdout. Exit codes: 0 ok, 1 invalid spec or files not written,
 * 2 files written but no picture.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import Ajv2020, { type ErrorObject } from "ajv/dist/2020";
import JSZip from "jszip";
import { buildInstanceFiles, type InstanceFiles } from "../src/lib/exportInstance";
import { expectedDomCounts } from "../src/lib/headlessApi";
import type { ImportInstanceResult } from "../src/lib/importInstance";
import {
  buildEditorStateFromSpec,
  InstanceSpecError,
  toExportInput,
  type InstanceSpec,
} from "../src/lib/instanceSpec";

const EDITOR_ROOT = fileURLToPath(new URL("..", import.meta.url));
const SCHEMA_PATH = fileURLToPath(new URL("../../../JSON/instance_spec.schema.json", import.meta.url));
const PNG_NAME = "instance.png";
const ZIP_NAME = "instance.zip";
const READY_TIMEOUT_MS = 15_000;

type Options = {
  specPath: string;
  outDir: string;
  png: boolean;
  zip: boolean;
  url: string | null;
  timeoutMs: number;
  viewport: { width: number; height: number };
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
      timeout: { type: "string", default: "60000" },
      viewport: { type: "string", default: "1600x1000" },
    },
  });
  if (positionals.length !== 1) throw new UsageError("Expected exactly one spec file.");
  if (!values.out) throw new UsageError("Missing --out <dir>.");
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
    timeoutMs,
    viewport: { width: Number(vp[1]), height: Number(vp[2]) },
  };
}

function formatSchemaError(e: ErrorObject): string {
  const where = e.instancePath === "" ? "/" : e.instancePath;
  const extra =
    e.keyword === "additionalProperties"
      ? ` (${String((e.params as { additionalProperty?: string }).additionalProperty)})`
      : "";
  return `${where}: ${e.message ?? e.keyword}${extra}`;
}

async function validateSpec(raw: unknown): Promise<string[]> {
  const schema = JSON.parse(await readFile(SCHEMA_PATH, "utf8")) as object;
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  const validate = ajv.compile(schema);
  if (validate(raw)) return [];
  return (validate.errors ?? []).map(formatSchemaError);
}

type Failure = { ok: false; stage: "input" | "schema" | "semantic" | "files"; errors: string[] };

function fail(stage: Failure["stage"], errors: string[]): never {
  const failure: Failure = { ok: false, stage, errors };
  console.log(JSON.stringify(failure, null, 2));
  process.exit(1);
}

/** Render the state in the editor and return the PNG bytes. */
async function renderPng(state: ImportInstanceResult, opts: Options): Promise<Buffer> {
  const { createServer } = await import("vite");
  const { chromium } = await import("playwright");

  const server = opts.url
    ? null
    : await createServer({
        root: EDITOR_ROOT,
        configFile: path.join(EDITOR_ROOT, "vite.config.ts"),
        server: { host: "127.0.0.1", hmr: false, open: false },
        logLevel: "silent",
      });
  let browser: Awaited<ReturnType<typeof chromium.launch>> | null = null;
  try {
    let baseUrl = opts.url;
    if (server) {
      await server.listen();
      baseUrl = server.resolvedUrls?.local[0] ?? null;
      if (!baseUrl) throw new Error("The Vite dev server did not report a URL.");
    }
    const pageUrl = new URL(baseUrl!);
    pageUrl.searchParams.set("headless", "1");

    browser = await chromium.launch({
      executablePath: process.env.DARP_CHROMIUM_PATH || undefined,
    });
    const context = await browser.newContext({
      viewport: opts.viewport,
      deviceScaleFactor: 2,
      colorScheme: "light",
    });
    const page = await context.newPage();
    page.on("pageerror", (err) => console.error(`[page] ${err.message}`));
    await page.goto(pageUrl.toString(), { waitUntil: "load", timeout: opts.timeoutMs });
    await page.waitForFunction(() => window.__darpEditor !== undefined, undefined, {
      timeout: opts.timeoutMs,
    });

    await page.evaluate((s) => window.__darpEditor!.loadState(s), state);
    await page.evaluate(
      ([expected, timeoutMs]) => window.__darpEditor!.whenReady(expected, timeoutMs),
      [expectedDomCounts(state), READY_TIMEOUT_MS] as const,
    );
    const dataUrl = await page.evaluate(() => window.__darpEditor!.capturePng());
    if (!dataUrl) throw new Error("The editor returned no picture.");
    const comma = dataUrl.indexOf(",");
    return Buffer.from(dataUrl.slice(comma + 1), "base64");
  } finally {
    await browser?.close();
    await server?.close();
  }
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
    fail("input", [`${opts.specPath}: ${e instanceof Error ? e.message : String(e)}`]);
  }

  const schemaErrors = await validateSpec(raw);
  if (schemaErrors.length > 0) fail("schema", schemaErrors);

  let state: ImportInstanceResult;
  try {
    state = buildEditorStateFromSpec(raw as InstanceSpec);
  } catch (e) {
    if (e instanceof InstanceSpecError) fail("semantic", e.problems);
    throw e;
  }

  let files: InstanceFiles;
  try {
    files = buildInstanceFiles(toExportInput(state));
  } catch (e) {
    fail("files", [e instanceof Error ? e.message : String(e)]);
  }

  await mkdir(opts.outDir, { recursive: true });
  const written: Record<string, string> = {};
  for (const [name, text] of Object.entries(files)) {
    const filePath = path.join(opts.outDir, name);
    await writeFile(filePath, text);
    written[name] = filePath;
  }

  let png: Buffer | null = null;
  let pngError: string | null = null;
  if (opts.png) {
    try {
      png = await renderPng(state, opts);
      const pngPath = path.join(opts.outDir, PNG_NAME);
      await writeFile(pngPath, png);
      written[PNG_NAME] = pngPath;
    } catch (e) {
      pngError = e instanceof Error ? e.message : String(e);
    }
  }

  if (opts.zip) written[ZIP_NAME] = await writeZip(opts.outDir, files, png);

  const summary = {
    ok: pngError === null,
    outDir: opts.outDir,
    files: written,
    png: written[PNG_NAME] ?? null,
    ...(pngError !== null ? { pngError } : {}),
    counts: {
      nodes: state.nodes.length,
      edges: state.edges.length,
      vehicles: state.vehicles.length,
      requests: state.requests.length,
    },
    warnings: state.warnings,
  };
  console.log(JSON.stringify(summary, null, 2));
  return pngError === null ? 0 : 2;
}

main(process.argv.slice(2)).then(
  (code) => process.exit(code),
  (e) => {
    if (e instanceof UsageError) {
      console.error(`build-instance: ${e.message}`);
      console.error(
        "usage: build-instance <spec.json> --out <dir> [--no-png] [--zip] [--url <editor url>] [--timeout <ms>] [--viewport <w>x<h>]",
      );
    } else {
      console.error(e instanceof Error ? (e.stack ?? e.message) : String(e));
    }
    process.exit(1);
  },
);
