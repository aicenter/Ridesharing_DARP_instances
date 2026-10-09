/**
 * Renders an editor state to a PNG by loading it into the real editor (`?headless=1`) in a
 * headless Chromium driven by Playwright.
 */
import type { Browser, LaunchOptions } from "playwright";
import { expectedDomCounts } from "../src/lib/headlessApi";
import type { ImportInstanceResult } from "../src/lib/importInstance";

export type Viewport = { width: number; height: number };

export const DEFAULT_VIEWPORT: Viewport = { width: 1600, height: 1000 };

/** Time the editor gets to lay out and paint a loaded state. */
const READY_TIMEOUT_MS = 15_000;

export type RendererOptions = {
  /** Chromium/Chrome binary; default: the one Playwright installed. */
  chromiumPath?: string | null;
  viewport?: Viewport;
};

export class EditorRenderer {
  private readonly browser: Browser;
  private readonly viewport: Viewport;

  private constructor(browser: Browser, viewport: Viewport) {
    this.browser = browser;
    this.viewport = viewport;
  }

  static async launch(opts: RendererOptions = {}): Promise<EditorRenderer> {
    const { chromium } = await import("playwright");
    const launch: LaunchOptions = { executablePath: opts.chromiumPath || undefined };
    const browser = await chromium.launch(launch);
    return new EditorRenderer(browser, opts.viewport ?? DEFAULT_VIEWPORT);
  }

  /**
   * Loads `state` into the editor served at `editorUrl` and returns the PNG. Every call uses a
   * fresh page, so the readiness check never sees the DOM of a previous instance.
   */
  async render(editorUrl: string, state: ImportInstanceResult, timeoutMs: number): Promise<Buffer> {
    const pageUrl = new URL(editorUrl);
    pageUrl.searchParams.set("headless", "1");

    const context = await this.browser.newContext({
      viewport: this.viewport,
      deviceScaleFactor: 2,
      colorScheme: "light",
    });
    try {
      const page = await context.newPage();
      page.on("pageerror", (err) => console.error(`[page] ${err.message}`));
      await page.goto(pageUrl.toString(), { waitUntil: "load", timeout: timeoutMs });
      await page.waitForFunction(() => window.__darpEditor !== undefined, undefined, {
        timeout: timeoutMs,
      });

      await page.evaluate((s) => window.__darpEditor!.loadState(s), state);
      await page.evaluate(
        ([expected, ms]) => window.__darpEditor!.whenReady(expected, ms),
        [expectedDomCounts(state), Math.min(READY_TIMEOUT_MS, timeoutMs)] as const,
      );
      const dataUrl = await page.evaluate(() => window.__darpEditor!.capturePng());
      if (!dataUrl) throw new Error("The editor returned no picture.");
      const comma = dataUrl.indexOf(",");
      return Buffer.from(dataUrl.slice(comma + 1), "base64");
    } finally {
      await context.close();
    }
  }

  async close(): Promise<void> {
    await this.browser.close();
  }
}
