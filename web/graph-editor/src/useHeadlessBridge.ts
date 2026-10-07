import type { Edge, ReactFlowInstance } from "@xyflow/react";
import { useEffect, useRef, type RefObject } from "react";
import type { RoadNodeType } from "./components/RoadNode";
import { captureCroppedFlowPng } from "./lib/captureFlowPng";
import { buildInstanceFiles } from "./lib/exportInstance";
import type { ExportSolutionInput } from "./lib/exportSolution";
import type { RoadEdgeData } from "./lib/graphModel";
import type { DarpEditorHeadlessApi, ExpectedDomCounts } from "./lib/headlessApi";
import type { ImportInstanceResult } from "./lib/importInstance";

type HeadlessBridgeDeps = {
  applyInstance: (data: ImportInstanceResult) => void;
  getExportInput: () => ExportSolutionInput;
  flowHostRef: RefObject<HTMLDivElement | null>;
  rfInstanceRef: RefObject<ReactFlowInstance<RoadNodeType, Edge<RoadEdgeData>> | null>;
};

const DEFAULT_READY_TIMEOUT_MS = 15_000;

function nextFrame(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error ?? new Error("Could not read the PNG blob."));
    reader.readAsDataURL(blob);
  });
}

function countRendered(host: HTMLElement): ExpectedDomCounts {
  return {
    nodes: host.querySelectorAll(".react-flow__node").length,
    edges: host.querySelectorAll(".react-flow__edge").length,
    vehicleChips: host.querySelectorAll(".road-node__vehicle-chip").length,
    requestChips: host.querySelectorAll(".road-node__request-chip").length,
  };
}

function describeMismatch(expected: ExpectedDomCounts, rendered: ExpectedDomCounts): string {
  return (Object.keys(expected) as Array<keyof ExpectedDomCounts>)
    .filter((k) => expected[k] !== rendered[k])
    .map((k) => `${k} ${rendered[k]}/${expected[k]}`)
    .join(", ");
}

/**
 * Register `window.__darpEditor` (see `lib/headlessApi.ts`) while `enabled`. The callbacks are
 * read at call time, so the registered object stays the same across renders.
 */
export function useHeadlessBridge(enabled: boolean, deps: HeadlessBridgeDeps): void {
  const latest = useRef(deps);
  useEffect(() => {
    latest.current = deps;
  });

  useEffect(() => {
    if (!enabled) return;

    const api: DarpEditorHeadlessApi = {
      loadState(state) {
        latest.current.applyInstance(state);
      },

      async whenReady(expected, timeoutMs = DEFAULT_READY_TIMEOUT_MS) {
        const deadline = performance.now() + timeoutMs;
        let mismatch = "page not mounted";
        for (;;) {
          const host = latest.current.flowHostRef.current;
          const rf = latest.current.rfInstanceRef.current;
          if (host && rf) {
            const rendered = countRendered(host);
            mismatch = describeMismatch(expected, rendered);
            const measured = rf
              .getNodes()
              .every((n) => (n.measured?.width ?? 0) > 0 && (n.measured?.height ?? 0) > 0);
            if (!measured) mismatch = [mismatch, "nodes not measured"].filter(Boolean).join(", ");
            if (mismatch === "") break;
          }
          if (performance.now() > deadline) {
            throw new Error(`The editor did not render the state within ${timeoutMs} ms: ${mismatch}.`);
          }
          await nextFrame();
        }
        await document.fonts.ready;
        await nextFrame();
        await nextFrame();
      },

      async capturePng() {
        const host = latest.current.flowHostRef.current;
        const rf = latest.current.rfInstanceRef.current;
        if (!host || !rf) throw new Error("The editor is not mounted.");
        const blob = await captureCroppedFlowPng(host, rf, rf.getNodes());
        return blob ? blobToDataUrl(blob) : null;
      },

      buildFiles() {
        return buildInstanceFiles(latest.current.getExportInput());
      },
    };

    window.__darpEditor = api;
    return () => {
      if (window.__darpEditor === api) delete window.__darpEditor;
    };
  }, [enabled]);
}
