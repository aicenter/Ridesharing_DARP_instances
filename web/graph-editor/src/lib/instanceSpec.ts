import type { Edge } from "@xyflow/react";
import type { RoadNodeType } from "../components/RoadNode";
import { buildDistanceMatrix, buildNodeIndex, type ExportSolutionInput } from "./exportSolution";
import {
  handleIdsForDirectedEdge,
  makeEdgeId,
  newRoadEdge,
  newRoadNode,
  type ProblemType,
  type RequestState,
  type RoadEdgeData,
  type VehicleState,
} from "./graphModel";
import type { ImportInstanceResult } from "./importInstance";
import { layoutImportGraph } from "./layoutImportGraph";
import { computeOnboardTiming } from "./onboardTiming";
import { buildInitialSolution } from "./solutionModel";

/** Instance spec as described by `JSON/instance_spec.schema.json`. */
export type SpecNode = { id: number; x?: number; y?: number };
export type SpecEdge = { from: number; to: number; travel_time: number; bidirectional?: boolean };
export type SpecOnboardRequest = { request: number; pickup_time?: number };
export type SpecVehicle = {
  position: number;
  capacity: number;
  en_route_to?: number;
  remaining_time?: number;
  onboard?: SpecOnboardRequest[];
};
export type SpecRequest = { id: number; origin: number; destination: number; time: number };
export type SpecSettings = {
  problem?: ProblemType;
  max_delay_seconds?: number;
  current_time?: number;
  layout_unit_px?: number;
};
export type InstanceSpec = {
  nodes: SpecNode[];
  edges: SpecEdge[];
  vehicles?: SpecVehicle[];
  requests?: SpecRequest[];
  settings?: SpecSettings;
};

/** Pixels per layout unit of the spec node positions. */
export const DEFAULT_LAYOUT_UNIT_PX = 256;

/** The editor snaps node positions to this grid. */
const GRID_PX = 16;

/** All problems of a spec that the schema cannot express, found in one pass. */
export class InstanceSpecError extends Error {
  readonly problems: string[];

  constructor(problems: string[]) {
    super(problems.join("\n"));
    this.name = "InstanceSpecError";
    this.problems = problems;
  }
}

function snapToGrid(v: number): number {
  return Math.round(v / GRID_PX) * GRID_PX;
}

function nodePositions(
  nodes: SpecNode[],
  edges: Array<{ from: number; to: number }>,
  unitPx: number,
  problems: string[],
): Array<{ x: number; y: number }> {
  const withPosition = nodes.filter((n) => n.x !== undefined && n.y !== undefined);
  const partial = nodes.filter((n) => (n.x === undefined) !== (n.y === undefined));
  for (const n of partial) {
    problems.push(`node ${n.id}: both x and y must be given, or neither.`);
  }
  // Only edges between existing nodes take part in the layout; the others are reported.
  const n = nodes.length;
  const layoutEdges = edges.filter((e) => e.from < n && e.to < n);
  if (withPosition.length === 0 || partial.length > 0) {
    return layoutImportGraph(n, layoutEdges);
  }
  if (withPosition.length !== nodes.length) {
    const missing = nodes.filter((n) => n.x === undefined && n.y === undefined).map((n) => n.id);
    problems.push(
      `nodes ${missing.join(", ")}: positions must be given for all nodes or for none.`,
    );
    return layoutImportGraph(n, layoutEdges);
  }
  return nodes.map((n) => ({ x: snapToGrid(n.x! * unitPx), y: snapToGrid(n.y! * unitPx) }));
}

/**
 * Editor state (the shape the file import produces) for a spec. Throws an `InstanceSpecError`
 * listing every problem found; warnings about unusual but valid specs are returned in the state.
 */
export function buildEditorStateFromSpec(spec: InstanceSpec): ImportInstanceResult {
  const problems: string[] = [];
  const warnings: string[] = [];
  const settings = spec.settings ?? {};
  const problemType: ProblemType = settings.problem ?? "DARP";
  const unitPx = settings.layout_unit_px ?? DEFAULT_LAYOUT_UNIT_PX;

  // Nodes: ids must be exactly 0..n-1.
  const n = spec.nodes.length;
  const seenIds = new Set<number>();
  for (const node of spec.nodes) {
    if (seenIds.has(node.id)) problems.push(`node ${node.id}: duplicate id.`);
    seenIds.add(node.id);
    if (node.id >= n) {
      problems.push(`node ${node.id}: ids must be 0..${n - 1} (${n} nodes).`);
    }
  }
  const knownNode = (id: number): boolean => seenIds.has(id);

  // Edges, with the bidirectional shorthand expanded.
  const directed: Array<{ from: number; to: number; w: number }> = [];
  const seenEdges = new Set<string>();
  spec.edges.forEach((e, i) => {
    const label = `edge ${i} (${e.from} → ${e.to})`;
    if (!knownNode(e.from)) problems.push(`${label}: unknown node ${e.from}.`);
    if (!knownNode(e.to)) problems.push(`${label}: unknown node ${e.to}.`);
    if (e.from === e.to) problems.push(`${label}: self-loop.`);
    if (e.travel_time === 0) warnings.push(`${label}: travel time is 0.`);
    const arcs = e.bidirectional ? [[e.from, e.to], [e.to, e.from]] : [[e.from, e.to]];
    for (const [from, to] of arcs) {
      const key = `${from}>${to}`;
      if (seenEdges.has(key)) {
        problems.push(`${label}: duplicate directed edge ${from} → ${to}.`);
        continue;
      }
      seenEdges.add(key);
      directed.push({ from, to, w: e.travel_time });
    }
  });

  const nodesSorted = [...spec.nodes].sort((a, b) => a.id - b.id);
  const positions = nodePositions(nodesSorted, directed, unitPx, problems);
  const nodes: RoadNodeType[] = nodesSorted.map((node, i) =>
    newRoadNode(String(node.id), node.id, positions[i] ?? { x: 48 + i * 32, y: 48 }),
  );
  const nodeById = new Map(nodes.map((node) => [node.id, node]));

  const edges: Edge<RoadEdgeData>[] = [];
  for (const e of directed) {
    const source = nodeById.get(String(e.from));
    const target = nodeById.get(String(e.to));
    if (!source || !target) continue;
    edges.push({
      ...newRoadEdge(source.id, target.id, e.w),
      ...handleIdsForDirectedEdge(source, target),
    });
  }
  const travelTimeOf = new Map(directed.map((e) => [`${e.from}>${e.to}`, e.w]));

  // Requests.
  const requests: RequestState[] = [];
  const requestById = new Map<number, RequestState>();
  for (const r of spec.requests ?? []) {
    const label = `request ${r.id}`;
    if (requestById.has(r.id)) {
      problems.push(`${label}: duplicate id.`);
      continue;
    }
    if (!knownNode(r.origin)) problems.push(`${label}: unknown origin node ${r.origin}.`);
    if (!knownNode(r.destination)) {
      problems.push(`${label}: unknown destination node ${r.destination}.`);
    }
    if (r.origin === r.destination) problems.push(`${label}: origin equals destination.`);
    const request: RequestState = {
      id: r.id,
      pickupTimeSeconds: r.time,
      originNodeId: String(r.origin),
      destinationNodeId: String(r.destination),
      onboardVehicleId: null,
      onboardPickupTimeSeconds: null,
    };
    requests.push(request);
    requestById.set(r.id, request);
  }
  requests.sort((a, b) => a.id - b.id);

  // Vehicles: the array index is the vehicle id.
  const vehicles: VehicleState[] = [];
  (spec.vehicles ?? []).forEach((v, id) => {
    const label = `vehicle ${id}`;
    if (!knownNode(v.position)) problems.push(`${label}: unknown position node ${v.position}.`);
    let location: VehicleState["location"] = { kind: "node", nodeId: String(v.position) };
    if (v.en_route_to !== undefined) {
      const travelTime = travelTimeOf.get(`${v.position}>${v.en_route_to}`);
      const remaining = v.remaining_time ?? 0;
      if (travelTime === undefined) {
        problems.push(`${label}: no edge ${v.position} → ${v.en_route_to} to be en route on.`);
      } else if (travelTime === 0) {
        problems.push(`${label}: cannot be en route on the edge ${v.position} → ${v.en_route_to} with travel time 0.`);
      } else if (remaining > travelTime) {
        problems.push(
          `${label}: remaining_time ${remaining} exceeds the travel time ${travelTime} of the edge ${v.position} → ${v.en_route_to}.`,
        );
      } else {
        location = {
          kind: "edge",
          edgeId: makeEdgeId(String(v.position), String(v.en_route_to)),
          progress: 1 - remaining / travelTime,
        };
      }
    }
    const vehicle: VehicleState = { id, capacity: v.capacity, location };
    vehicles.push(vehicle);

    const onboard = v.onboard ?? [];
    if (onboard.length > v.capacity) {
      problems.push(`${label}: ${onboard.length} onboard requests exceed the capacity ${v.capacity}.`);
    }
    for (const o of onboard) {
      const request = requestById.get(o.request);
      if (!request) {
        problems.push(`${label}: unknown onboard request ${o.request}.`);
        continue;
      }
      if (request.onboardVehicleId !== null) {
        problems.push(
          `${label}: request ${o.request} is already onboard vehicle ${request.onboardVehicleId}.`,
        );
        continue;
      }
      request.onboardVehicleId = id;
      request.onboardPickupTimeSeconds = o.pickup_time ?? null;
    }
  });
  if (problemType === "fleet-sizing" && vehicles.length > 0) {
    warnings.push(
      "fleet-sizing instance with vehicles: they are written to vehicle_data.json, not vehicles.csv.",
    );
  }

  if (problems.length > 0) throw new InstanceSpecError(problems);

  // Reachability and the timing of the onboard requests.
  const idToIndex = buildNodeIndex(nodes);
  const dm = buildDistanceMatrix(edges, idToIndex);
  for (const r of requests) {
    const o = idToIndex.get(r.originNodeId!)!;
    const d = idToIndex.get(r.destinationNodeId!)!;
    if (!Number.isFinite(dm[o][d])) {
      warnings.push(`request ${r.id}: destination ${d} is not reachable from origin ${o}.`);
    }
  }
  const currentTimeSeconds = settings.current_time ?? null;
  const timing = computeOnboardTiming(vehicles, requests, edges, idToIndex, dm, currentTimeSeconds);
  for (const r of timing.unreachable) {
    problems.push(
      `request ${r.id}: cannot be onboard vehicle ${r.onboardVehicleId}, there is no path from its origin to the vehicle.`,
    );
  }
  if (timing.now < timing.minNow) {
    problems.push(
      `settings.current_time ${timing.now} is too early: the vehicles with onboard requests cannot be at their positions before ${timing.minNow}.`,
    );
  }
  if (problems.length > 0) throw new InstanceSpecError(problems);

  return {
    nodes,
    edges,
    vehicles,
    requests,
    problemType,
    maxDelaySeconds: settings.max_delay_seconds ?? null,
    currentTimeSeconds,
    nextLogicalId: n,
    nextVehicleId: vehicles.length,
    nextRequestId: requests.reduce((m, r) => Math.max(m, r.id + 1), 0),
    warnings,
  };
}

/** Export input for an editor state, with the solution the Export button would use. */
export function toExportInput(state: ImportInstanceResult): ExportSolutionInput {
  return {
    nodes: state.nodes,
    edges: state.edges,
    vehicles: state.vehicles,
    requests: state.requests,
    solutionItems: buildInitialSolution(state.vehicles, state.requests),
    problemType: state.problemType,
    maxDelaySeconds: state.maxDelaySeconds,
    currentTimeSeconds: state.currentTimeSeconds,
  };
}
