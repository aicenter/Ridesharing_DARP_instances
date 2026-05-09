/**
 * Default travel time (seconds) for new directed edges when linking two nodes.
 * Both directions created on connect use this initial value; each arc can be edited separately.
 */
export const DEFAULT_TRAVEL_TIME_SECONDS = 60;

/** Default seat capacity when a new vehicle is placed on a node. */
export const DEFAULT_VEHICLE_CAPACITY = 4;

/** Default pickup time for a newly created request (seconds). */
export const DEFAULT_REQUEST_PICKUP_TIME_SECONDS = 0;

export type VehicleState = {
  id: number;
  capacity: number;
};

export type RequestState = {
  id: number;
  pickupTimeSeconds: number;
  originNodeId: string | null;
  destinationNodeId: string | null;
};

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
