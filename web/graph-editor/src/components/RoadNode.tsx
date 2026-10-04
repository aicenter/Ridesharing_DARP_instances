import { Fragment, useCallback, type DragEvent, type MouseEvent } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import {
  GRAPH_EDITOR_DND_MIME,
  useGraphEditor,
  type DndPayload,
} from "../GraphEditorContext";
import { parseDndPayload } from "../lib/dndPayload";
import type { RequestBadge } from "../lib/graphModel";
import { RequestGlyph } from "./RequestGlyph";
import { VehicleChip } from "./VehicleChip";

export type RoadNodeData = {
  logicalId: number;
  requestBadges: RequestBadge[];
};

export type RoadNodeType = Node<RoadNodeData, "road">;

const SIDES = [
  { position: Position.Top, id: "top" },
  { position: Position.Right, id: "right" },
  { position: Position.Bottom, id: "bottom" },
  { position: Position.Left, id: "left" },
] as const;

export function RoadNode({ id, data }: NodeProps<RoadNodeType>) {
  const {
    vehicles,
    addVehicle,
    moveVehicle,
    requests,
    selectedRequest,
    selectRequest,
    addRequestToNode,
    dropRequestOnNode,
    setRequestOnboard,
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
      const payload = parseDndPayload(raw);
      if (!payload) return;
      if (payload.kind === "new-vehicle") {
        addVehicle({ kind: "node", nodeId: id });
        return;
      }
      if (payload.kind === "new-request") {
        addRequestToNode(id);
        return;
      }
      if (payload.kind === "vehicle") {
        moveVehicle(payload.vehicleId, { kind: "node", nodeId: id });
        return;
      }
      if (payload.kind === "request") {
        if (payload.fromVehicle) {
          setRequestOnboard(payload.requestId, null);
        } else {
          dropRequestOnNode(payload.requestId, id);
        }
      }
    },
    [id, addVehicle, moveVehicle, addRequestToNode, dropRequestOnNode, setRequestOnboard],
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

  const nodeVehicles = vehicles.filter(
    (v) => v.location.kind === "node" && v.location.nodeId === id,
  );
  const hasVehicles = nodeVehicles.length > 0;
  const hasRequests = data.requestBadges.length > 0;
  const requestSelected = (r: RequestBadge) => selectedRequest?.requestId === r.id;
  const onboardVehicleId = (r: RequestBadge) =>
    requests.find((x) => x.id === r.id)?.onboardVehicleId ?? null;

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
            {nodeVehicles.map((v) => (
              <VehicleChip key={v.id} vehicle={v} />
            ))}
          </div>
        ) : null}
        {hasRequests ? (
          <div className="road-node__requests">
            {data.requestBadges.map((r) => {
              const onboardOn = onboardVehicleId(r);
              const onboardNote = onboardOn !== null ? `, onboard vehicle ${onboardOn}` : "";
              return (
                <div
                  key={`${r.role}-${r.id}`}
                  className={`road-node__request-chip nodrag${requestSelected(r) ? " road-node__request-chip--selected" : ""}${onboardOn !== null ? " road-node__request-chip--onboard" : ""}`}
                  draggable
                  onDragStart={(e) => onRequestChipDragStart(e, r.id)}
                  onClick={(e) => onRequestChipClick(e, r.id)}
                  title={
                    r.role === "origin"
                      ? `Request ${r.id} pickup at t=${r.pickupTimeSeconds}s${onboardNote} (drag to set/move, or onto a vehicle to put it onboard)`
                      : `Request ${r.id} dropoff${onboardNote} (drag to move / reset origin, or onto a vehicle to put it onboard)`
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
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
}
