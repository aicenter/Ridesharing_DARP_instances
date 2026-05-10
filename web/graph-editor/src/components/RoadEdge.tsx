import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useReactFlow,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { useCallback, type CSSProperties, type MouseEvent } from "react";
import { DEFAULT_TRAVEL_TIME_SECONDS, type RoadEdgeData } from "../lib/graphModel";

export type RoadEdgeType = Edge<RoadEdgeData, "road">;

/** Perpendicular separation (px) so opposite arcs between the same nodes do not overlap. */
const BIDIRECTIONAL_OFFSET = 14;

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
  const { setEdges } = useReactFlow();

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

  return (
    <>
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
      </EdgeLabelRenderer>
    </>
  );
}
