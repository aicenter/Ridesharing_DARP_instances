import type { Edge } from "@xyflow/react";
import type { RoadNodeType } from "../components/RoadNode";
import {
  actionId,
  parseActionId,
  vehiclePlanContainerId,
  type SolutionItems,
} from "./solutionModel";
import {
  vehicleNextLocation,
  vehicleStartNodeId,
  type ProblemType,
  type RequestState,
  type RoadEdgeData,
  type VehicleState,
} from "./graphModel";
import { computeOnboardTiming, type OnboardTiming } from "./onboardTiming";
import { dijkstraAllPairs } from "./shortestPaths";

/** Upper bound for time windows when the instance has no maximum delay (seconds). */
const DEFAULT_MAX_TIME_SLACK = 10 * 24 * 3600;

export type ExportSolutionInput = {
  nodes: RoadNodeType[];
  edges: Edge<RoadEdgeData>[];
  vehicles: VehicleState[];
  requests: RequestState[];
  solutionItems: SolutionItems;
  problemType: ProblemType;
  /** Maximum delay of the instance (`max_delay`, absolute mode); `null` if not set. */
  maxDelaySeconds: number | null;
  /** Current time set by the user; `null` derives it from the onboard requests. */
  currentTimeSeconds: number | null;
};

/** Graph data shared by the exports: exported node indices and travel times between them. */
type GraphIndex = {
  idToIndex: Map<string, number>;
  dm: number[][];
};

/** Timing of the onboard requests for an export; throws if the state on the map is not consistent. */
export function resolveOnboardTiming(
  input: Pick<ExportSolutionInput, "edges" | "vehicles" | "requests" | "currentTimeSeconds">,
  { idToIndex, dm }: GraphIndex,
): OnboardTiming {
  const timing = computeOnboardTiming(
    input.vehicles,
    input.requests,
    input.edges,
    idToIndex,
    dm,
    input.currentTimeSeconds,
  );
  if (timing.unreachable.length > 0) {
    const r = timing.unreachable[0];
    throw new Error(
      `Request R${r.id} cannot be onboard vehicle ${r.onboardVehicleId}: there is no path from ` +
        `the request origin to the vehicle.`,
    );
  }
  if (timing.now < timing.minNow) {
    throw new Error(
      `Current time ${timing.now}s is too early: the vehicles with onboard requests cannot be at ` +
        `their positions before ${timing.minNow}s.`,
    );
  }
  return timing;
}

/** Export node ids as 0..n-1 by sorting by logicalId. */
export function buildNodeIndex(nodes: RoadNodeType[]): Map<string, number> {
  const nodesSorted = [...nodes].sort((a, b) => a.data.logicalId - b.data.logicalId);
  const idToIndex = new Map<string, number>();
  nodesSorted.forEach((node, idx) => idToIndex.set(node.id, idx));
  return idToIndex;
}

/** All-pairs shortest travel times over the directed edges, indexed by exported node index. */
export function buildDistanceMatrix(
  edges: Edge<RoadEdgeData>[],
  idToIndex: Map<string, number>,
): number[][] {
  const n = idToIndex.size;
  const adj: Array<Array<{ to: number; w: number }>> = Array.from({ length: n }, () => []);
  for (const e of edges) {
    const s = idToIndex.get(e.source);
    const t = idToIndex.get(e.target);
    const w = e.data?.travelTime;
    if (s === undefined || t === undefined) continue;
    if (w === undefined || !Number.isFinite(w) || w < 0) continue;
    adj[s].push({ to: t, w });
  }
  return dijkstraAllPairs(n, adj);
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

/**
 * The solution is edited separately from the map, so it can lag behind the onboard state:
 * an onboard request must have no pickup action and its drop-off must be on its vehicle's plan.
 */
function assertSolutionMatchesOnboardState(items: SolutionItems, requests: RequestState[]): void {
  for (const r of requests) {
    if (r.onboardVehicleId === null) continue;
    const pickupPlaced = Object.values(items).some((list) =>
      list.includes(actionId("pickup", r.id)),
    );
    const dropOffOnVehicle = (
      items[vehiclePlanContainerId(r.onboardVehicleId)] ?? []
    ).includes(actionId("dropoff", r.id));
    if (pickupPlaced || !dropOffOnVehicle) {
      throw new Error(
        `The solution is out of date: request R${r.id} is onboard vehicle ${r.onboardVehicleId}. ` +
          `Use "Reset from graph" in the Solution panel.`,
      );
    }
  }
}

type PlanAction = {
  id: number;
  request_index: number;
  type: "pickup" | "drop_off";
  position: { index: number };
  min_time: number;
  max_time: number;
  service_duration: number;
};

type SimulatedAction = {
  arrival_time: number;
  departure_time: number;
  action: PlanAction;
};

export type VehiclePlanJson = {
  cost: number;
  vehicle: { index: number; capacity: number; init_position: { index: number } };
  departure_time: number;
  arrival_time: number;
  actions: SimulatedAction[];
};

/**
 * With a maximum delay, the latest times follow the instance specification: the latest pickup is
 * the desired pickup time + maximum delay, the latest drop-off adds the minimal travel time.
 */
function makeAction(
  id: number,
  r: RequestState,
  kind: "pickup" | "drop_off",
  { idToIndex, dm }: GraphIndex,
  maxDelaySeconds: number | null,
): PlanAction {
  const nodeIndex = (nodeId: string): number => {
    const idx = idToIndex.get(nodeId);
    if (idx === undefined) {
      throw new Error(`Node ${nodeId} not found for request R${r.id}.`);
    }
    return idx;
  };
  const origin = nodeIndex(r.originNodeId!);
  const destination = nodeIndex(r.destinationNodeId!);
  const desiredPickupTime = Math.max(0, Math.round(r.pickupTimeSeconds));
  const minTime = kind === "pickup" ? desiredPickupTime : 0;

  let maxTime = minTime + DEFAULT_MAX_TIME_SLACK;
  if (maxDelaySeconds !== null) {
    maxTime =
      kind === "pickup"
        ? desiredPickupTime + maxDelaySeconds
        : desiredPickupTime + dm[origin][destination] + maxDelaySeconds;
  }
  return {
    id,
    request_index: r.id,
    type: kind,
    position: { index: kind === "pickup" ? origin : destination },
    min_time: minTime,
    max_time: maxTime,
    service_duration: 0,
  };
}

/**
 * @param startNodeIndex node the plan continues from: the vehicle's node, or the target of its edge
 * @param now current time of the instance, see `computeOnboardTiming`
 * @param timeToStartNode remaining time to reach `startNodeIndex` (0 unless the vehicle is en route)
 * @param onboardPickups requests already in the vehicle with their pickup times, in pickup order;
 * they open the plan
 */
function simulateVehiclePlan(
  planKeys: string[],
  startNodeIndex: number,
  now: number,
  timeToStartNode: number,
  onboardPickups: Array<{ request: RequestState; time: number }>,
  graph: GraphIndex,
  maxDelaySeconds: number | null,
  requestsById: Map<number, RequestState>,
  nextStopId: { value: number },
): { driveCost: number; departure_time: number; arrival_time: number; actions: SimulatedAction[] } {
  const { dm } = graph;
  // The plan of a vehicle with passengers started with its first pickup; the cost covers the
  // time driven since then.
  const planDeparture = onboardPickups.length > 0 ? onboardPickups[0].time : now;

  let pos = startNodeIndex;
  let t = now + timeToStartNode;
  let driveCost = t - planDeparture;
  const actions: SimulatedAction[] = [];

  // Onboard pickups already happened; they add no travel.
  for (const { request, time } of onboardPickups) {
    const action = makeAction(nextStopId.value++, request, "pickup", graph, maxDelaySeconds);
    actions.push({ arrival_time: time, departure_time: time, action });
  }

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
    const action = makeAction(
      nextStopId.value++,
      req,
      parsed.kind === "pickup" ? "pickup" : "drop_off",
      graph,
      maxDelaySeconds,
    );
    const nodeIndex = action.position.index;

    const d = dm[pos][nodeIndex];
    if (!Number.isFinite(d)) {
      throw new Error(
        `No driving path from node ${pos} to node ${nodeIndex} (request R${parsed.requestId}).`,
      );
    }
    driveCost += Math.round(d);
    t += Math.round(d);
    const arrivalAtStop = t;

    const serviceStart = Math.max(arrivalAtStop, action.min_time);
    const departureFromStop = serviceStart + action.service_duration;
    t = departureFromStop;
    pos = nodeIndex;

    actions.push({
      arrival_time: arrivalAtStop,
      departure_time: departureFromStop,
      action,
    });
  }

  return {
    driveCost,
    departure_time: planDeparture,
    arrival_time: t,
    actions,
  };
}

export type VehiclePlanExport = {
  vehicle: VehicleState;
  /** Index of the vehicle in the exported fleet (vehicles sorted by id). */
  fleetIndex: number;
  /** Exported index of the node the vehicle starts from (edge source if it is en route). */
  initNodeIndex: number;
  /** Edge target and remaining travel time for an en-route vehicle. */
  nextLocation: { nodeIndex: number; remainingTime: number } | null;
  /** Requests in the vehicle, in pickup order. */
  onboardRequests: RequestState[];
  /** True if the plan has neither onboard pickups nor actions from the Solution panel. */
  empty: boolean;
  plan: VehiclePlanJson;
};

/**
 * One plan per vehicle on the map (matching `JSON/vehicle_plan.schema.json`), ordered by fleet
 * index. Action ids are numbered from 1 across the plans.
 */
export function buildVehiclePlans(
  input: ExportSolutionInput,
  graph: GraphIndex,
): VehiclePlanExport[] {
  const { edges, vehicles, requests, solutionItems, maxDelaySeconds } = input;
  const { idToIndex } = graph;
  assertSolutionMatchesOnboardState(solutionItems, requests);

  const timing = resolveOnboardTiming(input, graph);

  const requestsById = new Map(requests.map((r) => [r.id, r]));
  const nodeIndex = (nodeId: string): number => {
    const idx = idToIndex.get(nodeId);
    if (idx === undefined) throw new Error(`Node ${nodeId} not found.`);
    return idx;
  };

  const nextStopId = { value: 1 };
  return [...vehicles]
    .sort((a, b) => a.id - b.id)
    .map((vehicle, fleetIndex) => {
      const planKeys = solutionItems[vehiclePlanContainerId(vehicle.id)] ?? [];
      const onboardPickups = requests
        .filter((r) => r.onboardVehicleId === vehicle.id)
        .map((request) => ({ request, time: timing.pickupTimes.get(request.id)! }))
        .sort((a, b) => a.time - b.time || a.request.id - b.request.id);

      const initNodeIndex = nodeIndex(vehicleStartNodeId(vehicle, edges));
      const next = vehicleNextLocation(vehicle, edges);
      const nextLocation = next
        ? { nodeIndex: nodeIndex(next.nodeId), remainingTime: next.remainingTime }
        : null;

      const sim = simulateVehiclePlan(
        planKeys,
        nextLocation ? nextLocation.nodeIndex : initNodeIndex,
        timing.now,
        nextLocation ? nextLocation.remainingTime : 0,
        onboardPickups,
        graph,
        maxDelaySeconds,
        requestsById,
        nextStopId,
      );

      return {
        vehicle,
        fleetIndex,
        initNodeIndex,
        nextLocation,
        onboardRequests: onboardPickups.map((p) => p.request),
        empty: sim.actions.length === 0,
        plan: {
          cost: sim.driveCost,
          vehicle: {
            index: fleetIndex,
            capacity: vehicle.capacity,
            init_position: { index: initNodeIndex },
          },
          departure_time: sim.departure_time,
          arrival_time: sim.arrival_time,
          actions: sim.actions,
        },
      };
    });
}

/**
 * Build a JSON object matching `JSON/solution.schema.json` (plans follow `vehicle_plan.schema.json`).
 */
export function buildSolutionExportObject(input: ExportSolutionInput): Record<string, unknown> {
  const { nodes, edges, requests, solutionItems, maxDelaySeconds } = input;
  if (nodes.length === 0) {
    throw new Error("Cannot export solution: no nodes in the graph.");
  }

  const idToIndex = buildNodeIndex(nodes);
  const dm = buildDistanceMatrix(edges, idToIndex);
  const graph: GraphIndex = { idToIndex, dm };

  for (const containerId of Object.keys(solutionItems)) {
    if (!containerId.startsWith("v:")) continue;
    const vehicleId = Number(containerId.slice(2));
    if (solutionItems[containerId].length > 0 && !input.vehicles.some((v) => v.id === vehicleId)) {
      throw new Error(`Vehicle ${vehicleId} is in the solution but not on the map.`);
    }
  }

  const vehiclePlans = buildVehiclePlans(input, graph);
  const plans = vehiclePlans.filter((p) => !p.empty).map((p) => p.plan);

  const { dropped: droppedRequests } = classifyRequests(solutionItems, requests);
  let nextStopId = plans.reduce((s, p) => s + p.actions.length, 0) + 1;
  const droppedPayload = droppedRequests.map((r) => {
    const o = idToIndex.get(r.originNodeId!) ?? 0;
    const d = idToIndex.get(r.destinationNodeId!) ?? 0;
    const minTravel = Number.isFinite(dm[o][d]) ? Math.round(dm[o][d]) : 0;
    const baseId = nextStopId;
    nextStopId += 2;
    return {
      index: r.id,
      pickup: makeAction(baseId, r, "pickup", graph, maxDelaySeconds),
      drop_off: makeAction(baseId + 1, r, "drop_off", graph, maxDelaySeconds),
      min_travel_time: minTravel,
    };
  });

  const cost = plans.reduce((s, p) => s + p.cost, 0);
  const cost_minutes = Math.round(cost / 60);

  return {
    cost,
    cost_minutes,
    // The vehicles of a fleet-sizing instance are a part of the solution.
    ...(input.problemType === "fleet-sizing"
      ? {
          problem: input.problemType,
          vehicles: vehiclePlans.map((p) => ({
            index: p.fleetIndex,
            capacity: p.vehicle.capacity,
            initial_location: p.initNodeIndex,
          })),
        }
      : {}),
    plans: plans as unknown[],
    dropped_requests: droppedPayload as unknown[],
  };
}

export function exportSolutionJsonString(input: ExportSolutionInput): string {
  const obj = buildSolutionExportObject(input);
  return `${JSON.stringify(obj, null, 2)}\n`;
}
