/**
 * Renders the Open Graph preview image (`public/og.png`, 1200x630) from the picture of the
 * tiny example instance (`resources/tiny-instance/instance.png`) with Playwright Chromium.
 * Run `npm run og-image` after changing the picture or the title.
 */
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const WIDTH = 1200;
const HEIGHT = 630;
const TITLE = "DARP instance sketcher";
const SUBTITLE = "Draw a road network, place vehicles and requests, export a DARP instance.";

const SOURCE_PNG = fileURLToPath(new URL("../../../resources/tiny-instance/instance.png", import.meta.url));
const OUTPUT_PNG = fileURLToPath(new URL("../public/og.png", import.meta.url));

function pageHtml(pngDataUrl: string): string {
  return `<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body { margin: 0; width: ${WIDTH}px; height: ${HEIGHT}px; overflow: hidden; }
  body {
    display: flex; flex-direction: column; box-sizing: border-box;
    padding: 44px 56px 40px;
    font-family: system-ui, "Segoe UI", Roboto, sans-serif; color: #18181b;
    background: #fff;
  }
  h1 { margin: 0; font-size: 56px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.1; }
  p { margin: 10px 0 0; font-size: 26px; color: #52525b; }
  .pic {
    flex: 1 1 auto; margin-top: 26px; display: flex; align-items: center; justify-content: center;
    border: 2px solid #e4e4e7; border-radius: 14px; background: #fafafa; overflow: hidden;
  }
  .pic img { max-width: 94%; max-height: 90%; object-fit: contain; }
</style></head>
<body>
  <h1>${TITLE}</h1>
  <p>${SUBTITLE}</p>
  <div class="pic"><img src="${pngDataUrl}" alt=""></div>
</body></html>`;
}

async function main(): Promise<void> {
  const png = await readFile(SOURCE_PNG);
  const dataUrl = `data:image/png;base64,${png.toString("base64")}`;
  const browser = await chromium.launch({ executablePath: process.env.DARP_CHROMIUM_PATH || undefined });
  try {
    const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1 });
    await page.setContent(pageHtml(dataUrl), { waitUntil: "load" });
    const out = await page.screenshot({ type: "png", clip: { x: 0, y: 0, width: WIDTH, height: HEIGHT } });
    await writeFile(OUTPUT_PNG, out);
    console.log(`wrote ${OUTPUT_PNG} (${out.length} bytes)`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
