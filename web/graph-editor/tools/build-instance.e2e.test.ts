/**
 * End-to-end test of the headless instance builder; needs a Chromium that Playwright can launch
 * (`npx playwright install chromium`). Opt in with `DARP_E2E=1 npm test`.
 */
import { execFile } from "node:child_process";
import { mkdtemp, readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { describe, expect, it } from "vitest";

const EDITOR_ROOT = fileURLToPath(new URL("..", import.meta.url));
const TSX_CLI = path.join(EDITOR_ROOT, "node_modules", "tsx", "dist", "cli.mjs");
const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47]);

async function runBuilder(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  try {
    const { stdout, stderr } = await promisify(execFile)(
      process.execPath,
      [TSX_CLI, path.join(EDITOR_ROOT, "tools", "build-instance.ts"), ...args],
      { cwd: EDITOR_ROOT, maxBuffer: 16 * 1024 * 1024 },
    );
    return { code: 0, stdout, stderr };
  } catch (e) {
    const err = e as { code?: number; stdout?: string; stderr?: string };
    return { code: err.code ?? 1, stdout: err.stdout ?? "", stderr: err.stderr ?? "" };
  }
}

describe.skipIf(!process.env.DARP_E2E)("build-instance (end to end)", () => {
  it("writes the instance files and a picture", { timeout: 180_000 }, async () => {
    const outDir = await mkdtemp(path.join(tmpdir(), "darp-instance-"));
    const result = await runBuilder([
      path.join(EDITOR_ROOT, "examples", "small-darp.json"),
      "--out",
      outDir,
      "--zip",
    ]);

    expect(result.stderr).toBe("");
    expect(result.code).toBe(0);
    const summary = JSON.parse(result.stdout) as { ok: boolean; files: Record<string, string> };
    expect(summary.ok).toBe(true);
    expect(Object.keys(summary.files).sort()).toEqual([
      "config.yaml",
      "dm.csv",
      "instance.png",
      "instance.zip",
      "requests.csv",
      "vehicle_data.json",
      "vehicles.csv",
    ]);

    const png = await readFile(path.join(outDir, "instance.png"));
    expect(png.subarray(0, 4)).toEqual(PNG_MAGIC);
    expect(png.length).toBeGreaterThan(5_000);
    expect((await stat(path.join(outDir, "instance.zip"))).size).toBeGreaterThan(5_000);
  });
});

describe("build-instance (no browser)", () => {
  it("rejects an invalid spec with the schema path", { timeout: 60_000 }, async () => {
    const outDir = await mkdtemp(path.join(tmpdir(), "darp-instance-"));
    const specPath = path.join(outDir, "bad.json");
    await (await import("node:fs/promises")).writeFile(
      specPath,
      JSON.stringify({ nodes: [{ id: 0 }], edges: [], vehicles: [{ position: 0, capacity: "4" }] }),
    );
    const result = await runBuilder([specPath, "--out", outDir, "--no-png"]);
    expect(result.code).toBe(1);
    expect(JSON.parse(result.stdout)).toEqual({
      ok: false,
      stage: "schema",
      errors: ["/vehicles/0/capacity: must be integer"],
    });
  });
});
