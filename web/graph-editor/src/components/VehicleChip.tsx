import { useCallback, type CSSProperties, type DragEvent, type MouseEvent } from "react";
import { GRAPH_EDITOR_DND_MIME, useGraphEditor, type DndPayload } from "../GraphEditorContext";
import { parseDndPayload } from "../lib/dndPayload";
import type { VehicleState } from "../lib/graphModel";
import { VehicleGlyph } from "./VehicleGlyph";

/** Vehicle chip shown on a node or along an edge; requests dropped on it become onboard. */
export function VehicleChip({
  vehicle,
  className,
  style,
}: {
  vehicle: VehicleState;
  className?: string;
  style?: CSSProperties;
}) {
  const {
    requests,
    selectedVehicle,
    selectVehicle,
    selectedRequest,
    selectRequest,
    setRequestOnboard,
  } = useGraphEditor();

  const onboard = requests.filter((r) => r.onboardVehicleId === vehicle.id);
  const selected = selectedVehicle?.vehicleId === vehicle.id;

  const onDragStart = useCallback(
    (e: DragEvent) => {
      e.stopPropagation();
      const payload: DndPayload = { kind: "vehicle", vehicleId: vehicle.id };
      e.dataTransfer.setData(GRAPH_EDITOR_DND_MIME, JSON.stringify(payload));
      e.dataTransfer.effectAllowed = "move";
    },
    [vehicle.id],
  );

  const onClick = useCallback(
    (e: MouseEvent) => {
      e.stopPropagation();
      selectVehicle({ vehicleId: vehicle.id });
    },
    [vehicle.id, selectVehicle],
  );

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
  }, []);

  const onDrop = useCallback(
    (e: DragEvent) => {
      const payload = parseDndPayload(e.dataTransfer.getData(GRAPH_EDITOR_DND_MIME));
      // Anything but a request is left to the node (or edge) under the chip.
      if (payload?.kind !== "request") return;
      e.preventDefault();
      e.stopPropagation();
      setRequestOnboard(payload.requestId, vehicle.id);
    },
    [vehicle.id, setRequestOnboard],
  );

  const onOnboardChipDragStart = useCallback((e: DragEvent, requestId: number) => {
    e.stopPropagation();
    const payload: DndPayload = { kind: "request", requestId, fromVehicle: true };
    e.dataTransfer.setData(GRAPH_EDITOR_DND_MIME, JSON.stringify(payload));
    e.dataTransfer.effectAllowed = "move";
  }, []);

  const onOnboardChipClick = useCallback(
    (e: MouseEvent, requestId: number) => {
      e.stopPropagation();
      selectRequest({ requestId });
    },
    [selectRequest],
  );

  return (
    <div
      className={`road-node__vehicle-chip nodrag${selected ? " road-node__vehicle-chip--selected" : ""}${className ? ` ${className}` : ""}`}
      style={style}
      draggable
      onDragStart={onDragStart}
      onClick={onClick}
      onDragOver={onDragOver}
      onDrop={onDrop}
      title={`Vehicle ${vehicle.id}, capacity ${vehicle.capacity} (drag to move; drop a request here to put it onboard)`}
    >
      <VehicleGlyph />
      <span className="road-node__vehicle-meta">
        <span className="road-node__vehicle-id">{vehicle.id}</span>
        <span className="road-node__vehicle-cap">cap {vehicle.capacity}</span>
      </span>
      {onboard.length > 0 ? (
        <span className="road-node__vehicle-onboard">
          {onboard.map((r) => (
            <span
              key={r.id}
              className={`road-node__onboard-chip${selectedRequest?.requestId === r.id ? " road-node__onboard-chip--selected" : ""}`}
              draggable
              onDragStart={(e) => onOnboardChipDragStart(e, r.id)}
              onClick={(e) => onOnboardChipClick(e, r.id)}
              title={`Request ${r.id} is onboard (drag to another vehicle, or onto a node to take it out)`}
            >
              R{r.id}
            </span>
          ))}
        </span>
      ) : null}
    </div>
  );
}
