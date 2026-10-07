import type { InstanceFiles } from "./exportInstance";
import type { ImportInstanceResult } from "./importInstance";

/** Elements the editor renders for a state; used to tell when the page shows all of it. */
export type ExpectedDomCounts = {
  nodes: number;
  edges: number;
  vehicleChips: number;
  requestChips: number;
};

/**
 * API the editor exposes as `window.__darpEditor` when opened with `?headless=1`; the headless
 * instance builder (`tools/build-instance.ts`) drives the editor through it.
 */
export type DarpEditorHeadlessApi = {
  /** Replace the editor state, as the file import does. */
  loadState(state: ImportInstanceResult): void;
  /** Resolves once the page shows `expected` and the layout has settled; rejects on timeout. */
  whenReady(expected: ExpectedDomCounts, timeoutMs?: number): Promise<void>;
  /** PNG of the graph (cropped to its content) as a data URL; `null` without nodes. */
  capturePng(): Promise<string | null>;
  /** The instance files the Export button would write. */
  buildFiles(): InstanceFiles;
};

declare global {
  interface Window {
    __darpEditor?: DarpEditorHeadlessApi;
  }
}

/** Every complete request has a pickup and a drop-off chip. */
export function expectedDomCounts(state: ImportInstanceResult): ExpectedDomCounts {
  return {
    nodes: state.nodes.length,
    edges: state.edges.length,
    vehicleChips: state.vehicles.length,
    requestChips:
      2 * state.requests.filter((r) => r.originNodeId !== null && r.destinationNodeId !== null).length,
  };
}
