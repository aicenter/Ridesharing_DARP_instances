/**
 * Default travel time (seconds) for new directed edges when linking two nodes.
 * Both directions created on connect use this initial value; each arc can be edited separately.
 */
export const DEFAULT_TRAVEL_TIME_SECONDS = 60;

/** Default seat capacity when a new vehicle is placed on a node. */
export const DEFAULT_VEHICLE_CAPACITY = 4;

/** Default pickup time for a newly created request (seconds). */
export const DEFAULT_REQUEST_PICKUP_TIME_SECONDS = 0;

/** A vehicle is either parked on a node or travelling along a directed edge. */
export type VehicleLocation =
  | { kind: "node"; nodeId: string }
  /** `progress` is the travelled fraction of the edge, 0 (source) to 1 (target). */
  | { kind: "edge"; edgeId: string; progress: number };

export type VehicleState = {
  id: number;
  capacity: number;
  location: VehicleLocation;
};

export type RequestState = {
  id: number;
  pickupTimeSeconds: number;
  originNodeId: string | null;
  destinationNodeId: string | null;
  /** Vehicle that already carries this request (picked up, not yet dropped off). */
  onboardVehicleId: number | null;
  /**
   * Pickup time of an onboard request set by the user; `null` leaves it to the heuristic in
   * `computeOnboardTiming`.
   */
  onboardPickupTimeSeconds: number | null;
};

/** In a fleet-sizing instance, the vehicles are not an input (no `vehicles.csv`). */
export type ProblemType = "DARP" | "fleet-sizing";

type EdgeEndpoints = { id: string; source: string; target: string };

function edgeOfVehicle<E extends EdgeEndpoints>(edgeId: string, edges: E[]): E {
  const edge = edges.find((e) => e.id === edgeId);
  if (!edge) throw new Error(`Edge ${edgeId} not found.`);
  return edge;
}

/** Node the vehicle starts from: its node, or the source of the edge it travels along. */
export function vehicleStartNodeId(vehicle: VehicleState, edges: EdgeEndpoints[]): string {
  const loc = vehicle.location;
  return loc.kind === "node" ? loc.nodeId : edgeOfVehicle(loc.edgeId, edges).source;
}

/** Remaining travel time (seconds) to the edge target for a vehicle at `progress`. */
export function remainingEdgeTravelTime(progress: number, travelTime: number): number {
  return Math.round((1 - progress) * travelTime);
}

/**
 * Where an en-route vehicle is heading: the target node of its edge and the remaining travel time.
 * `null` for a vehicle parked on a node.
 */
export function vehicleNextLocation(
  vehicle: VehicleState,
  edges: Array<EdgeEndpoints & { data?: RoadEdgeData }>,
): { nodeId: string; remainingTime: number } | null {
  const loc = vehicle.location;
  if (loc.kind === "node") return null;
  const edge = edgeOfVehicle(loc.edgeId, edges);
  return {
    nodeId: edge.target,
    remainingTime: remainingEdgeTravelTime(
      loc.progress,
      edge.data?.travelTime ?? DEFAULT_TRAVEL_TIME_SECONDS,
    ),
  };
}

export function formatVehicleLocation(vehicle: VehicleState, edges: EdgeEndpoints[]): string {
  const loc = vehicle.location;
  if (loc.kind === "node") return `node ${loc.nodeId}`;
  const edge = edgeOfVehicle(loc.edgeId, edges);
  return `edge ${edge.source} → ${edge.target}`;
}

export type RequestBadge = {
  id: number;
  pickupTimeSeconds: number;
  role: "origin" | "destination";
  otherNodeId: string | null;
};

export type RoadEdgeData = {
  travelTime: number;
};

export function makeEdgeId(sourceNodeId: string, targetNodeId: string): string {
  return `e-${sourceNodeId}-${targetNodeId}`;
}

export function hasDirectedEdge(
  edges: { source: string; target: string }[],
  source: string,
  target: string,
): boolean {
  return edges.some((e) => e.source === source && e.target === target);
}

/** Fallback size before React Flow measures the node (matches `.road-node` roughly). */
export const ROAD_NODE_FALLBACK_SIZE = { w: 56, h: 44 } as const;

export type NodeLayout = {
  position: { x: number; y: number };
  measured?: { width?: number; height?: number };
};

/**
 * Pick source/target handle ids so the edge leaves toward the neighbor and arrives from that side.
 * Handles on the node are `s-{top|right|bottom|left}` (source) and `t-{...}` (target).
 */
export function handleIdsForDirectedEdge(
  source: NodeLayout,
  target: NodeLayout,
  fallback = ROAD_NODE_FALLBACK_SIZE,
): { sourceHandle: string; targetHandle: string } {
  const sw = source.measured?.width ?? fallback.w;
  const sh = source.measured?.height ?? fallback.h;
  const tw = target.measured?.width ?? fallback.w;
  const th = target.measured?.height ?? fallback.h;

  const sx = source.position.x + sw / 2;
  const sy = source.position.y + sh / 2;
  const tx = target.position.x + tw / 2;
  const ty = target.position.y + th / 2;

  const dx = tx - sx;
  const dy = ty - sy;

  let sourceSide: "top" | "right" | "bottom" | "left";
  let targetSide: "top" | "right" | "bottom" | "left";

  if (Math.abs(dx) >= Math.abs(dy)) {
    if (dx > 0) {
      sourceSide = "right";
      targetSide = "left";
    } else {
      sourceSide = "left";
      targetSide = "right";
    }
  } else if (dy > 0) {
    sourceSide = "bottom";
    targetSide = "top";
  } else {
    sourceSide = "top";
    targetSide = "bottom";
  }

  return {
    sourceHandle: `s-${sourceSide}`,
    targetHandle: `t-${targetSide}`,
  };
}
