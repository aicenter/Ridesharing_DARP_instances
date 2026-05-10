import type { RequestState } from "./graphModel";

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

/** Container id → ordered draggable action ids (`p:3`, `d:3`, …). */
export type SolutionItems = Record<string, string[]>;

export type FleetVehicle = {
  vehicleId: number;
  nodeId: string;
  capacity: number;
};

export function fleetFromNodes(
  nodes: { id: string; data: { vehicles: { id: number; capacity: number }[] } }[],
): FleetVehicle[] {
  const out: FleetVehicle[] = [];
  for (const n of nodes) {
    for (const v of n.data.vehicles) {
      out.push({ vehicleId: v.id, nodeId: n.id, capacity: v.capacity });
    }
  }
  out.sort((a, b) => a.vehicleId - b.vehicleId);
  return out;
}

/** Add empty plan columns for new vehicles without discarding existing layout. */
export function ensureVehicleColumns(items: SolutionItems, vehicles: FleetVehicle[]): SolutionItems {
  let changed = false;
  const next = { ...items };
  for (const v of vehicles) {
    const k = vehiclePlanContainerId(v.vehicleId);
    if (!(k in next)) {
      next[k] = [];
      changed = true;
    }
  }
  return changed ? next : items;
}

export function buildInitialSolution(
  vehicles: FleetVehicle[],
  requests: RequestState[],
): SolutionItems {
  const complete = requests
    .filter((r) => r.originNodeId && r.destinationNodeId)
    .sort((a, b) => a.id - b.id);

  const pool: string[] = [];
  for (const r of complete) {
    pool.push(actionId("pickup", r.id), actionId("dropoff", r.id));
  }

  const sortedVehicles = [...vehicles].sort((a, b) => a.vehicleId - b.vehicleId);
  const out: SolutionItems = { [SOLUTION_POOL_ID]: pool };
  for (const v of sortedVehicles) {
    out[vehiclePlanContainerId(v.vehicleId)] = [];
  }
  return out;
}
