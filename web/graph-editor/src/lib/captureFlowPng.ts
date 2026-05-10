import type { Edge, ReactFlowInstance } from "@xyflow/react";
import { toPng } from "html-to-image";
import type { RoadNodeType } from "../components/RoadNode";
import type { RoadEdgeData } from "./graphModel";

const SCREEN_PADDING_PX = 48;

function flushLayout(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });
}

function expandRect(
  minL: number,
  minT: number,
  maxR: number,
  maxB: number,
  r: DOMRect,
): [number, number, number, number] {
  return [
    Math.min(minL, r.left),
    Math.min(minT, r.top),
    Math.max(maxR, r.right),
    Math.max(maxB, r.bottom),
  ];
}

function escapeId(id: string): string {
  return typeof CSS !== "undefined" && typeof CSS.escape === "function" ? CSS.escape(id) : id.replace(/"/g, '\\"');
}

/** Exclude UI chrome from PNG (controls, minimap, attribution). */
function exportFilter(node: unknown): boolean {
  if (!(node instanceof HTMLElement)) return true;
  const cls = node.classList;
  if (
    cls.contains("react-flow__controls") ||
    cls.contains("react-flow__minimap") ||
    cls.contains("react-flow__attribution") ||
    cls.contains("xy-flow__controls") ||
    cls.contains("xy-flow__minimap") ||
    cls.contains("xy-flow__attribution")
  ) {
    return false;
  }
  return true;
}

/**
 * Screen-space union of nodes, edge paths, and edge labels; crop is relative to the `.react-flow` pane.
 */
function computeContentBounds(
  pane: HTMLElement,
  viewportEl: HTMLElement,
  nodeIds: string[],
): { cropLeft: number; cropTop: number; cropW: number; cropH: number; cw: number; ch: number } {
  const paneRect = pane.getBoundingClientRect();
  let minL = Infinity;
  let minT = Infinity;
  let maxR = -Infinity;
  let maxB = -Infinity;
  let sawNode = false;

  for (const id of nodeIds) {
    const safe = escapeId(id);
    const el =
      (pane.querySelector(`[data-id="${safe}"].react-flow__node`) as HTMLElement | null) ??
      (pane.querySelector(`[data-id="${safe}"].xy-flow__node`) as HTMLElement | null);
    if (!el || !viewportEl.contains(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 && r.height < 1) continue;
    [minL, minT, maxR, maxB] = expandRect(minL, minT, maxR, maxB, r);
    sawNode = true;
  }

  viewportEl.querySelectorAll<SVGGraphicsElement>("g.react-flow__edge path, g.xy-flow__edge path").forEach(
    (path) => {
      const r = path.getBoundingClientRect();
      if (r.width < 1 && r.height < 1) return;
      [minL, minT, maxR, maxB] = expandRect(minL, minT, maxR, maxB, r);
    },
  );

  pane
    .querySelectorAll<HTMLElement>(
      ".react-flow__edgelabel-renderer button, .xy-flow__edgelabel-renderer button, [class*='edgelabel'] button",
    )
    .forEach((btn) => {
      const r = btn.getBoundingClientRect();
      if (r.width < 1 && r.height < 1) return;
      [minL, minT, maxR, maxB] = expandRect(minL, minT, maxR, maxB, r);
    });

  if (!sawNode || !Number.isFinite(minL)) {
    viewportEl.querySelectorAll<HTMLElement>(".react-flow__node, .xy-flow__node").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width < 1 && r.height < 1) return;
      [minL, minT, maxR, maxB] = expandRect(minL, minT, maxR, maxB, r);
      sawNode = true;
    });
  }

  const pad = SCREEN_PADDING_PX;
  minL -= pad;
  minT -= pad;
  maxR += pad;
  maxB += pad;

  let cropLeft = minL - paneRect.left;
  let cropTop = minT - paneRect.top;
  let cropW = maxR - minL;
  let cropH = maxB - minT;

  const cw = pane.clientWidth;
  const ch = pane.clientHeight;

  if (!Number.isFinite(cropW) || cropW < 2 || !Number.isFinite(cropH) || cropH < 2 || !sawNode) {
    cropLeft = 0;
    cropTop = 0;
    cropW = cw;
    cropH = ch;
  } else {
    cropLeft = Math.max(0, cropLeft);
    cropTop = Math.max(0, cropTop);
    cropW = Math.min(cropW, cw - cropLeft);
    cropH = Math.min(cropH, ch - cropTop);
  }

  if (cropW < 1 || cropH < 1) {
    cropLeft = 0;
    cropTop = 0;
    cropW = cw;
    cropH = ch;
  }

  return { cropLeft, cropTop, cropW, cropH, cw, ch };
}

export async function captureCroppedFlowPng(
  flowHost: HTMLElement,
  rf: ReactFlowInstance<RoadNodeType, Edge<RoadEdgeData>>,
  reactNodes: RoadNodeType[],
): Promise<Blob | null> {
  if (reactNodes.length === 0) return null;

  const pane = flowHost.querySelector(".react-flow") as HTMLElement | null;
  const viewportEl = flowHost.querySelector(".react-flow__viewport, .xy-flow__viewport") as HTMLElement | null;
  if (!pane || !viewportEl) return null;

  await rf.fitView({
    padding: 0.2,
    duration: 0,
    minZoom: 0.05,
    maxZoom: 2.5,
  });
  await flushLayout();

  const nodeIds = reactNodes.map((n) => n.id);
  const { cropLeft, cropTop, cropW, cropH, cw, ch } = computeContentBounds(pane, viewportEl, nodeIds);

  const pixelRatio = Math.min(2, window.devicePixelRatio || 1);

  // Avoid forcing width/height/overflow on the pane — that can break nested SVG edge layout
  // in html-to-image. Crop still uses pane client rect.
  const dataUrl = await toPng(pane, {
    backgroundColor: "#ffffff",
    pixelRatio,
    cacheBust: true,
    filter: exportFilter,
  });

  const img = new Image();
  img.decoding = "async";
  img.src = dataUrl;
  await img.decode();

  const scaleX = img.naturalWidth / cw;
  const scaleY = img.naturalHeight / ch;

  const sx = Math.max(0, Math.round(cropLeft * scaleX));
  const sy = Math.max(0, Math.round(cropTop * scaleY));
  const sw = Math.max(1, Math.round(cropW * scaleX));
  const sh = Math.max(1, Math.round(cropH * scaleY));

  const canvas = document.createElement("canvas");
  canvas.width = sw;
  canvas.height = sh;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, sw, sh);
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);

  return new Promise((resolve) => {
    canvas.toBlob((b) => resolve(b), "image/png");
  });
}
