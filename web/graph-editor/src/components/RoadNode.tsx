import { Fragment, useCallback, type DragEvent, type MouseEvent } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import {
  GRAPH_EDITOR_DND_MIME,
  useGraphEditor,
  type DndPayload,
} from "../GraphEditorContext";
import type { RequestBadge, VehicleState } from "../lib/graphModel";
import { VehicleGlyph } from "./VehicleGlyph";
import { RequestGlyph } from "./RequestGlyph";

export type RoadNodeData = {
  logicalId: number;
  vehicles: VehicleState[];
  requestBadges: RequestBadge[];
};

export type RoadNodeType = Node<RoadNodeData, "road">;

const SIDES = [
  { position: Position.Top, id: "top" },
  { position: Position.Right, id: "right" },
  { position: Position.Bottom, id: "bottom" },
  { position: Position.Left, id: "left" },
] as const;

function parsePayload(raw: string): DndPayload | null {
  try {
    const o = JSON.parse(raw) as unknown;
    if (!o || typeof o !== "object") return null;
    const rec = o as Record<string, unknown>;
    if (rec.kind === "new-vehicle") return { kind: "new-vehicle" };
    if (rec.kind === "new-request") return { kind: "new-request" };
    if (
      rec.kind === "vehicle" &&
      typeof rec.nodeId === "string" &&
      typeof rec.vehicleId === "number"
    ) {
      return { kind: "vehicle", nodeId: rec.nodeId, vehicleId: rec.vehicleId };
    }
    if (rec.kind === "request" && typeof rec.requestId === "number") {
      return { kind: "request", requestId: rec.requestId };
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function RoadNode({ id, data }: NodeProps<RoadNodeType>) {
  const {
    selectedVehicle,
    selectVehicle,
    addVehicleToNode,
    moveVehicle,
    selectedRequest,
    selectRequest,
    addRequestToNode,
    dropRequestOnNode,
  } = useGraphEditor();

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = e.dataTransfer.effectAllowed === "copy" ? "copy" : "move";
  }, []);

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const raw = e.dataTransfer.getData(GRAPH_EDITOR_DND_MIME);
      const payload = parsePayload(raw);
      if (!payload) return;
      if (payload.kind === "new-vehicle") {
        addVehicleToNode(id);
        return;
      }
      if (payload.kind === "new-request") {
        addRequestToNode(id);
        return;
      }
      if (payload.kind === "vehicle") {
        if (payload.nodeId !== id) {
          moveVehicle(payload.nodeId, payload.vehicleId, id);
        }
        return;
      }
      if (payload.kind === "request") {
        dropRequestOnNode(payload.requestId, id);
      }
    },
    [id, addVehicleToNode, moveVehicle, addRequestToNode, dropRequestOnNode],
  );

  const onVehicleChipDragStart = useCallback(
    (e: DragEvent, vehicleId: number) => {
      e.stopPropagation();
      const payload: DndPayload = { kind: "vehicle", nodeId: id, vehicleId };
      e.dataTransfer.setData(GRAPH_EDITOR_DND_MIME, JSON.stringify(payload));
      e.dataTransfer.effectAllowed = "move";
    },
    [id],
  );

  const onVehicleChipClick = useCallback(
    (e: MouseEvent, vehicleId: number) => {
      e.stopPropagation();
      selectVehicle({ nodeId: id, vehicleId });
    },
    [id, selectVehicle],
  );

  const onRequestChipDragStart = useCallback(
    (e: DragEvent, requestId: number) => {
      e.stopPropagation();
      const payload: DndPayload = { kind: "request", requestId };
      e.dataTransfer.setData(GRAPH_EDITOR_DND_MIME, JSON.stringify(payload));
      e.dataTransfer.effectAllowed = "move";
    },
    [],
  );

  const onRequestChipClick = useCallback(
    (e: MouseEvent, requestId: number) => {
      e.stopPropagation();
      selectRequest({ requestId });
    },
    [selectRequest],
  );

  const hasVehicles = data.vehicles.length > 0;
  const hasRequests = data.requestBadges.length > 0;
  const chipSelected = (v: VehicleState) =>
    selectedVehicle?.nodeId === id && selectedVehicle.vehicleId === v.id;
  const requestSelected = (r: RequestBadge) => selectedRequest?.requestId === r.id;

  return (
    <div
      className={`road-node${hasVehicles || hasRequests ? " road-node--with-vehicles" : ""}`}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {SIDES.map(({ position, id: sideId }) => (
        <Fragment key={sideId}>
          <Handle type="target" position={position} id={`t-${sideId}`} />
          <Handle type="source" position={position} id={`s-${sideId}`} />
        </Fragment>
      ))}
      <div className="road-node__body">
        <span className="road-node__label">{data.logicalId}</span>
        {hasVehicles ? (
          <div className="road-node__vehicles">
            {data.vehicles.map((v) => (
              <div
                key={v.id}
                className={`road-node__vehicle-chip nodrag${chipSelected(v) ? " road-node__vehicle-chip--selected" : ""}`}
                draggable
                onDragStart={(e) => onVehicleChipDragStart(e, v.id)}
                onClick={(e) => onVehicleChipClick(e, v.id)}
                title={`Vehicle ${v.id}, capacity ${v.capacity} (drag to move)`}
              >
                <VehicleGlyph />
                <span className="road-node__vehicle-meta">
                  <span className="road-node__vehicle-id">{v.id}</span>
                  <span className="road-node__vehicle-cap">cap {v.capacity}</span>
                </span>
              </div>
            ))}
          </div>
        ) : null}
        {hasRequests ? (
          <div className="road-node__requests">
            {data.requestBadges.map((r) => (
              <div
                key={`${r.role}-${r.id}`}
                className={`road-node__request-chip nodrag${requestSelected(r) ? " road-node__request-chip--selected" : ""}`}
                draggable
                onDragStart={(e) => onRequestChipDragStart(e, r.id)}
                onClick={(e) => onRequestChipClick(e, r.id)}
                title={
                  r.role === "origin"
                    ? `Request ${r.id} pickup at t=${r.pickupTimeSeconds}s (drag to set/move)`
                    : `Request ${r.id} dropoff (drag to move / reset origin)`
                }
              >
                <RequestGlyph />
                {r.role === "origin" ? (
                  <span className="road-node__request-meta">
                    <span className="road-node__request-id">R{r.id}</span>
                    <span className="road-node__request-time">t {r.pickupTimeSeconds}s</span>
                  </span>
                ) : (
                  <span className="road-node__request-meta">
                    <span className="road-node__request-id">R{r.id}</span>
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
