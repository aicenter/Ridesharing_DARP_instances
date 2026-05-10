import type { Edge } from "@xyflow/react";
import type { RoadNodeType } from "../components/RoadNode";
import { actionId, parseActionId, vehiclePlanContainerId, type SolutionItems } from "./solutionModel";
import type { RequestState, RoadEdgeData } from "./graphModel";
import { dijkstraAllPairs } from "./shortestPaths";

/** Upper bound for time windows when the editor has no latest time (seconds). */
const DEFAULT_MAX_TIME_SLACK = 10 * 24 * 3600;

export type ExportSolutionInput = {
  nodes: RoadNodeType[];
  edges: Edge<RoadEdgeData>[];
  requests: RequestState[];
  solutionItems: SolutionItems;
};

type NodeMaps = {
  nodesSorted: RoadNodeType[];
  idToIndex: Map<string, number>;
  n: number;
};

function buildNodeMaps(nodes: RoadNodeType[]): NodeMaps {
  const nodesSorted = [...nodes].sort((a, b) => a.data.logicalId - b.data.logicalId);
  const idToIndex = new Map<string, number>();
  nodesSorted.forEach((node, idx) => idToIndex.set(node.id, idx));
  return { nodesSorted, idToIndex, n: nodesSorted.length };
}

function buildAdjacency(
  n: number,
  edges: Edge<RoadEdgeData>[],
  idToIndex: Map<string, number>,
): Array<Array<{ to: number; w: number }>> {
  const adj: Array<Array<{ to: number; w: number }>> = Array.from({ length: n }, () => []);
  for (const e of edges) {
    const s = idToIndex.get(e.source);
    const t = idToIndex.get(e.target);
    const w = e.data?.travelTime;
    if (s === undefined || t === undefined) continue;
    if (w === undefined || !Number.isFinite(w) || w < 0) continue;
    adj[s].push({ to: t, w });
  }
  return adj;
}

/** True if this action chip sits on some vehicle’s plan (any `v:*` list), not only Unassigned. */
function isActionOnAnyVehiclePlan(items: SolutionItems, actionKey: string): boolean {
  for (const [cid, list] of Object.entries(items)) {
    if (!cid.startsWith("v:")) continue;
    if (list.includes(actionKey)) return true;
  }
  return false;
}

/**
 * Dropped = complete request whose pickup is on no vehicle plan and drop-off is on no vehicle plan
 * (both may still appear only in Unassigned, or not at all).
 */
function classifyRequests(
  items: SolutionItems,
  requests: RequestState[],
): { dropped: RequestState[] } {
  const complete = requests.filter((r) => r.originNodeId && r.destinationNodeId);
  const dropped: RequestState[] = [];

  for (const r of complete) {
    const pKey = actionId("pickup", r.id);
    const dKey = actionId("dropoff", r.id);
    const pickupOnVehicle = isActionOnAnyVehiclePlan(items, pKey);
    const dropOnVehicle = isActionOnAnyVehiclePlan(items, dKey);
    if (!pickupOnVehicle && !dropOnVehicle) {
      dropped.push(r);
    }
  }

  return { dropped };
}

type SimulatedAction = {
  arrival_time: number;
  departure_time: number;
  action: {
    id: number;
    request_index: number;
    type: "pickup" | "drop_off";
    position: { index: number };
    min_time: number;
    max_time: number;
    service_duration: number;
  };
};

function simulateVehiclePlan(
  planKeys: string[],
  startNodeIndex: number,
  dm: number[][],
  requestsById: Map<number, RequestState>,
  idToIndex: Map<string, number>,
  nextStopId: { value: number },
): { driveCost: number; departure_time: number; arrival_time: number; actions: SimulatedAction[] } {
  let pos = startNodeIndex;
  let t = 0;
  let driveCost = 0;
  const actions: SimulatedAction[] = [];

  const planDeparture = 0;

  for (const key of planKeys) {
    const parsed = parseActionId(key);
    if (!parsed) {
      throw new Error(`Unknown action key in plan: ${key}`);
    }
    const req = requestsById.get(parsed.requestId);
    if (!req || !req.originNodeId || !req.destinationNodeId) {
      throw new Error(
        `Request R${parsed.requestId} is missing origin/destination; remove it from the plan or fix the request.`,
      );
    }
    const nodeId = parsed.kind === "pickup" ? req.originNodeId : req.destinationNodeId;
    const nodeIndex = idToIndex.get(nodeId);
    if (nodeIndex === undefined) {
      throw new Error(`Node ${nodeId} not found for request R${parsed.requestId}.`);
    }

    const d = dm[pos][nodeIndex];
    if (!Number.isFinite(d)) {
      throw new Error(
        `No driving path from node ${pos} to node ${nodeIndex} (request R${parsed.requestId}).`,
      );
    }
    driveCost += Math.round(d);
    t += Math.round(d);
    const arrivalAtStop = t;

    const minTime =
      parsed.kind === "pickup"
        ? Math.max(0, Math.round(req.pickupTimeSeconds))
        : 0;
    const serviceStart = Math.max(arrivalAtStop, minTime);
    const serviceDuration = 0;
    const departureFromStop = serviceStart + serviceDuration;
    t = departureFromStop;
    pos = nodeIndex;

    const maxTime =
      parsed.kind === "pickup"
        ? minTime + DEFAULT_MAX_TIME_SLACK
        : minTime + DEFAULT_MAX_TIME_SLACK;

    actions.push({
      arrival_time: arrivalAtStop,
      departure_time: departureFromStop,
      action: {
        id: nextStopId.value++,
        request_index: req.id,
        type: parsed.kind === "pickup" ? "pickup" : "drop_off",
        position: { index: nodeIndex },
        min_time: minTime,
        max_time: maxTime,
        service_duration: serviceDuration,
      },
    });
  }

  return {
    driveCost,
    departure_time: planDeparture,
    arrival_time: t,
    actions,
  };
}

function makeUnservedLeg(
  id: number,
  r: RequestState,
  kind: "pickup" | "drop_off",
  idToIndex: Map<string, number>,
): {
  id: number;
  request_index: number;
  type: "pickup" | "drop_off";
  position: { index: number };
  min_time: number;
  max_time: number;
  service_duration: number;
} {
  const nodeId = kind === "pickup" ? r.originNodeId! : r.destinationNodeId!;
  const idx = idToIndex.get(nodeId) ?? 0;
  const minTime =
    kind === "pickup" ? Math.max(0, Math.round(r.pickupTimeSeconds)) : 0;
  return {
    id,
    request_index: r.id,
    type: kind,
    position: { index: idx },
    min_time: minTime,
    max_time: minTime + DEFAULT_MAX_TIME_SLACK,
    service_duration: 0,
  };
}

/**
 * Build a JSON object matching `JSON/solution_schema.json` (plans follow `vehicle_plan_schema.json`).
 */
export function buildSolutionExportObject(input: ExportSolutionInput): Record<string, unknown> {
  const { nodes, edges, requests, solutionItems } = input;
  if (nodes.length === 0) {
    throw new Error("Cannot export solution: no nodes in the graph.");
  }

  const { idToIndex, n } = buildNodeMaps(nodes);
  const adj = buildAdjacency(n, edges, idToIndex);
  const dm = dijkstraAllPairs(n, adj);

  const requestsById = new Map(requests.map((r) => [r.id, r]));
  const { dropped: droppedRequests } = classifyRequests(solutionItems, requests);

  const vehicleById = new Map(
    nodes
      .flatMap((node) =>
        node.data.vehicles.map((v) => ({
          vehicleId: v.id,
          nodeId: node.id,
          capacity: v.capacity,
        })),
      )
      .map((x) => [x.vehicleId, x]),
  );

  const allVehicleIdsSorted = [...vehicleById.keys()].sort((a, b) => a - b);
  const vehicleIdToFleetIndex = new Map(allVehicleIdsSorted.map((id, i) => [id, i]));

  const vehicleIdsWithColumns = Object.keys(solutionItems)
    .filter((k) => k.startsWith("v:"))
    .map((k) => Number(k.slice(2)))
    .sort((a, b) => a - b);

  const nextStopId = { value: 1 };
  const plans: Array<Record<string, unknown> & { cost: number }> = [];

  for (const vehicleId of vehicleIdsWithColumns) {
    const planKeys = solutionItems[vehiclePlanContainerId(vehicleId)] ?? [];
    if (planKeys.length === 0) continue;

    const fleet = vehicleById.get(vehicleId);
    if (!fleet) {
      throw new Error(`Vehicle ${vehicleId} is in the solution but not on the map.`);
    }
    const startIdx = idToIndex.get(fleet.nodeId);
    if (startIdx === undefined) {
      throw new Error(`Start node ${fleet.nodeId} for vehicle ${vehicleId} not found.`);
    }

    const fleetIndex = vehicleIdToFleetIndex.get(vehicleId);
    if (fleetIndex === undefined) {
      throw new Error(`Internal: missing fleet index for vehicle ${vehicleId}.`);
    }

    const sim = simulateVehiclePlan(
      planKeys,
      startIdx,
      dm,
      requestsById,
      idToIndex,
      nextStopId,
    );

    plans.push({
      cost: sim.driveCost,
      vehicle: {
        index: fleetIndex,
        capacity: fleet.capacity,
        init_position: { index: startIdx },
      },
      departure_time: sim.departure_time,
      arrival_time: sim.arrival_time,
      actions: sim.actions,
    });
  }

  const droppedPayload = droppedRequests.map((r) => {
    const o = idToIndex.get(r.originNodeId!) ?? 0;
    const d = idToIndex.get(r.destinationNodeId!) ?? 0;
    const minTravel = Number.isFinite(dm[o][d]) ? Math.round(dm[o][d]) : 0;
    const baseId = nextStopId.value;
    nextStopId.value += 2;
    return {
      index: r.id,
      pickup: makeUnservedLeg(baseId, r, "pickup", idToIndex),
      drop_off: makeUnservedLeg(baseId + 1, r, "drop_off", idToIndex),
      min_travel_time: minTravel,
    };
  });

  const cost = plans.reduce((s, p) => s + p.cost, 0);
  const cost_minutes = Math.round(cost / 60);

  return {
    cost,
    cost_minutes,
    plans: plans as unknown[],
    dropped_requests: droppedPayload as unknown[],
  };
}

export function exportSolutionJsonString(input: ExportSolutionInput): string {
  const obj = buildSolutionExportObject(input);
  return `${JSON.stringify(obj, null, 2)}\n`;
}
