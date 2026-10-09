/**
 * Entry point of the instance builder service. Serves the built editor (`dist/`) and
 * `POST /instances`; see `app.ts`. Environment: `PORT` (default 8080), `DARP_CHROMIUM_PATH`,
 * `DARP_NO_RENDER=1` (no browser; for tests), `DARP_MAX_NODES|EDGES|VEHICLES|REQUESTS`.
 */
import { fileURLToPath } from "node:url";
import { EditorRenderer } from "../tools/editorRenderer";
import { loadSpecValidator } from "../tools/instancePipeline";
import { createApp, DEFAULT_LIMITS, type SpecLimits } from "./app";

const DIST_DIR = fileURLToPath(new URL("../dist", import.meta.url));

function limitsFromEnv(): SpecLimits {
  const limits = { ...DEFAULT_LIMITS };
  for (const key of Object.keys(limits) as Array<keyof SpecLimits>) {
    const value = process.env[`DARP_MAX_${key.toUpperCase()}`];
    if (value !== undefined) limits[key] = Number(value);
  }
  return limits;
}

async function main(): Promise<void> {
  const port = Number(process.env.PORT ?? 8080);
  const renderer =
    process.env.DARP_NO_RENDER === "1"
      ? null
      : await EditorRenderer.launch({ chromiumPath: process.env.DARP_CHROMIUM_PATH });
  const server = createApp({
    validate: await loadSpecValidator(),
    distDir: DIST_DIR,
    renderer,
    limits: limitsFromEnv(),
  });

  const shutdown = () => {
    server.close(() => {
      void (renderer?.close() ?? Promise.resolve()).finally(() => process.exit(0));
    });
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);

  server.listen(port, "0.0.0.0", () => {
    console.error(`instance builder listening on http://0.0.0.0:${port}/ (pictures: ${renderer ? "on" : "off"})`);
  });
}

main().catch((e: unknown) => {
  console.error(e instanceof Error ? (e.stack ?? e.message) : String(e));
  process.exit(1);
});
