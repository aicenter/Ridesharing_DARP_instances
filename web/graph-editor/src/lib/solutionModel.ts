import type { RequestState, VehicleState } from "./graphModel";

/** Unassigned pickup/dropoff chips live in this container. */
export const SOLUTION_POOL_ID = "pool";

export function vehiclePlanContainerId(vehicleId: number): string {
  return `v:${vehicleId}`;
}

export type PlanActionKind = "pickup" | "dropoff";

export function actionId(kind: PlanActionKind, requestId: number): string {
  return kind === "pickup" ? `p:${requestId}` : `d:${requestId}`;
}

export function parseActionId(s: string): { kind: PlanActionKind; requestId: number } | null {
  if (s.startsWith("p:")) {
    const n = Number(s.slice(2));
    return Number.isFinite(n) ? { kind: "pickup", requestId: n } : null;
  }
  if (s.startsWith("d:")) {
    const n = Number(s.slice(2));
    return Number.isFinite(n) ? { kind: "dropoff", requestId: n } : null;
  }
  return null;
}

export function formatActionLabel(actionKey: string): string {
  const p = parseActionId(actionKey);
  if (!p) return actionKey;
  return p.kind === "pickup" ? `Pickup R${p.requestId}` : `Dropoff R${p.requestId}`;
}

/**
 * Container id → ordered draggable action ids (`p:3`, `d:3`, …).
 * An onboard request has no pickup action (it is already picked up); its drop-off stays in the
 * plan of the vehicle that carries it.
 */
export type SolutionItems = Record<string, string[]>;

/** Add empty plan columns for new vehicles without discarding existing layout. */
export function ensureVehicleColumns(items: SolutionItems, vehicles: VehicleState[]): SolutionItems {
  let changed = false;
  const next = { ...items };
  for (const v of vehicles) {
    const k = vehiclePlanContainerId(v.id);
    if (!(k in next)) {
      next[k] = [];
      changed = true;
    }
  }
  return changed ? next : items;
}

export function buildInitialSolution(
  vehicles: VehicleState[],
  requests: RequestState[],
): SolutionItems {
  const complete = requests
    .filter((r) => r.originNodeId && r.destinationNodeId)
    .sort((a, b) => a.id - b.id);

  const sortedVehicles = [...vehicles].sort((a, b) => a.id - b.id);
  const out: SolutionItems = { [SOLUTION_POOL_ID]: [] };
  for (const v of sortedVehicles) {
    out[vehiclePlanContainerId(v.id)] = [];
  }

  for (const r of complete) {
    if (r.onboardVehicleId !== null) {
      out[vehiclePlanContainerId(r.onboardVehicleId)].push(actionId("dropoff", r.id));
    } else {
      out[SOLUTION_POOL_ID].push(actionId("pickup", r.id), actionId("dropoff", r.id));
    }
  }
  return out;
}
