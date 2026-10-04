import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useReactFlow,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { useCallback, type CSSProperties, type DragEvent, type MouseEvent } from "react";
import { GRAPH_EDITOR_DND_MIME, useGraphEditor } from "../GraphEditorContext";
import { parseDndPayload } from "../lib/dndPayload";
import { DEFAULT_TRAVEL_TIME_SECONDS, type RoadEdgeData } from "../lib/graphModel";
import { VehicleChip } from "./VehicleChip";

export type RoadEdgeType = Edge<RoadEdgeData, "road">;

/** Perpendicular separation (px) so opposite arcs between the same nodes do not overlap. */
const BIDIRECTIONAL_OFFSET = 14;

/** Samples used to find the point of the edge curve nearest to a dropped vehicle. */
const PROGRESS_SAMPLES = 100;

type Point = { x: number; y: number };

/** Control points of the single cubic segment (`M p0 C p1 p2 p3`) produced by `getBezierPath`. */
function bezierControlPoints(path: string): [Point, Point, Point, Point] {
  const c = path.match(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi)!.map(Number);
  return [
    { x: c[0], y: c[1] },
    { x: c[2], y: c[3] },
    { x: c[4], y: c[5] },
    { x: c[6], y: c[7] },
  ];
}

function bezierPoint([p0, p1, p2, p3]: [Point, Point, Point, Point], t: number): Point {
  const u = 1 - t;
  const a = u * u * u;
  const b = 3 * u * u * t;
  const c = 3 * u * t * t;
  const d = t * t * t;
  return {
    x: a * p0.x + b * p1.x + c * p2.x + d * p3.x,
    y: a * p0.y + b * p1.y + c * p2.y + d * p3.y,
  };
}

function nearestProgress(points: [Point, Point, Point, Point], target: Point): number {
  let best = 0;
  let bestDist = Number.POSITIVE_INFINITY;
  for (let i = 0; i <= PROGRESS_SAMPLES; i++) {
    const t = i / PROGRESS_SAMPLES;
    const p = bezierPoint(points, t);
    const dist = (p.x - target.x) ** 2 + (p.y - target.y) ** 2;
    if (dist < bestDist) {
      bestDist = dist;
      best = t;
    }
  }
  return best;
}

export function RoadEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  selected,
  data,
}: EdgeProps<RoadEdgeType>) {
  const { setEdges, screenToFlowPosition } = useReactFlow();
  const { vehicles, addVehicle, moveVehicle } = useGraphEditor();

  // Offset along the left normal of (source → target). For the reverse edge, (dx,dy) flips,
  // so the normal flips too — opposite directions get opposite shifts. An extra sign from
  // node ids used to cancel that and stacked both edges on the same line.
  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const ox = (-dy / len) * BIDIRECTIONAL_OFFSET;
  const oy = (dx / len) * BIDIRECTIONAL_OFFSET;

  const sx = sourceX + ox;
  const sy = sourceY + oy;
  const tx = targetX + ox;
  const ty = targetY + oy;

  const [path, labelX, labelY] = getBezierPath({
    sourceX: sx,
    sourceY: sy,
    sourcePosition,
    targetX: tx,
    targetY: ty,
    targetPosition,
    curvature: 0.22,
  });

  const travelTime = data?.travelTime ?? DEFAULT_TRAVEL_TIME_SECONDS;

  const onLabelClick = useCallback(
    (e: MouseEvent<HTMLButtonElement>) => {
      e.stopPropagation();
      setEdges((edges) => edges.map((edge) => ({ ...edge, selected: edge.id === id })));
    },
    [id, setEdges],
  );

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = e.dataTransfer.effectAllowed === "copy" ? "copy" : "move";
  }, []);

  // A vehicle dropped on the edge is placed at the nearest point of the curve.
  const onDrop = useCallback(
    (e: DragEvent) => {
      const payload = parseDndPayload(e.dataTransfer.getData(GRAPH_EDITOR_DND_MIME));
      if (payload?.kind !== "new-vehicle" && payload?.kind !== "vehicle") return;
      e.preventDefault();
      e.stopPropagation();
      const dropPoint = screenToFlowPosition(
        { x: e.clientX, y: e.clientY },
        { snapToGrid: false },
      );
      const progress = nearestProgress(bezierControlPoints(path), dropPoint);
      if (payload.kind === "new-vehicle") {
        addVehicle({ kind: "edge", edgeId: id, progress });
      } else {
        moveVehicle(payload.vehicleId, { kind: "edge", edgeId: id, progress });
      }
    },
    [id, path, screenToFlowPosition, addVehicle, moveVehicle],
  );

  const edgeVehicles = vehicles.filter(
    (v) => v.location.kind === "edge" && v.location.edgeId === id,
  );
  const controlPoints = edgeVehicles.length > 0 ? bezierControlPoints(path) : null;

  return (
    <>
      <g onDragOver={onDragOver} onDrop={onDrop}>
        <BaseEdge
          id={id}
          path={path}
          markerEnd={markerEnd}
          interactionWidth={20}
          style={{
            ...(style as CSSProperties | undefined),
            // Explicit paint so html-to-image captures paths (CSS-variable stroke can rasterize empty).
            stroke: "#6b7280",
            fill: "none",
            strokeWidth: selected ? 3 : 2,
          }}
        />
      </g>
      <EdgeLabelRenderer>
        <button
          type="button"
          className={`road-edge__label nodrag nopan${selected ? " road-edge__label--selected" : ""}`}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
          onClick={onLabelClick}
        >
          {travelTime}s
        </button>
        {controlPoints
          ? edgeVehicles.map((v) => {
              if (v.location.kind !== "edge") return null;
              const p = bezierPoint(controlPoints, v.location.progress);
              return (
                <VehicleChip
                  key={v.id}
                  vehicle={v}
                  className="road-edge__vehicle nopan"
                  style={{ transform: `translate(-50%, -50%) translate(${p.x}px, ${p.y}px)` }}
                />
              );
            })
          : null}
      </EdgeLabelRenderer>
    </>
  );
}
