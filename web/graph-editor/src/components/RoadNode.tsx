import { Fragment, useCallback, type DragEvent, type MouseEvent } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import {
  GRAPH_EDITOR_DND_MIME,
  useGraphEditor,
  type DndPayload,
} from "../GraphEditorContext";
import type { VehicleState } from "../lib/graphModel";
import { VehicleGlyph } from "./VehicleGlyph";

export type RoadNodeData = {
  logicalId: number;
  vehicles: VehicleState[];
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
    if (
      rec.kind === "vehicle" &&
      typeof rec.nodeId === "string" &&
      typeof rec.vehicleId === "number"
    ) {
      return { kind: "vehicle", nodeId: rec.nodeId, vehicleId: rec.vehicleId };
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function RoadNode({ id, data }: NodeProps<RoadNodeType>) {
  const { selectedVehicle, selectVehicle, addVehicleToNode, moveVehicle } = useGraphEditor();

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
      if (payload.kind === "vehicle") {
        if (payload.nodeId !== id) {
          moveVehicle(payload.nodeId, payload.vehicleId, id);
        }
      }
    },
    [id, addVehicleToNode, moveVehicle],
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

  const hasVehicles = data.vehicles.length > 0;
  const chipSelected = (v: VehicleState) =>
    selectedVehicle?.nodeId === id && selectedVehicle.vehicleId === v.id;

  return (
    <div
      className={`road-node${hasVehicles ? " road-node--with-vehicles" : ""}`}
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
      </div>
    </div>
  );
}
