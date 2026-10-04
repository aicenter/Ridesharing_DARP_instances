import { createContext, useContext, type ReactNode } from "react";
import type { RequestState, VehicleLocation, VehicleState } from "./lib/graphModel";

export const GRAPH_EDITOR_DND_MIME = "application/graph-editor";

export type DndNewVehicle = { kind: "new-vehicle" };
export type DndNewRequest = { kind: "new-request" };

export type DndMoveVehicle = {
  kind: "vehicle";
  vehicleId: number;
};

export type DndMoveRequest = {
  kind: "request";
  requestId: number;
  /** Set when the drag started from the onboard chip inside a vehicle. */
  fromVehicle?: boolean;
};

export type DndPayload = DndNewVehicle | DndMoveVehicle | DndNewRequest | DndMoveRequest;

export type SelectedVehicle = { vehicleId: number };
export type SelectedRequest = { requestId: number };

export type GraphEditorContextValue = {
  vehicles: VehicleState[];
  selectedVehicle: SelectedVehicle | null;
  selectVehicle: (sel: SelectedVehicle | null) => void;
  addVehicle: (location: VehicleLocation) => void;
  moveVehicle: (vehicleId: number, location: VehicleLocation) => void;
  setVehicleCapacity: (vehicleId: number, capacity: number) => void;
  removeVehicle: (vehicleId: number) => void;

  requests: RequestState[];
  selectedRequest: SelectedRequest | null;
  selectRequest: (sel: SelectedRequest | null) => void;
  addRequestToNode: (nodeId: string) => void;
  dropRequestOnNode: (requestId: number, nodeId: string) => void;
  setRequestPickupTime: (requestId: number, pickupTimeSeconds: number) => void;
  removeRequest: (requestId: number) => void;
  /** Put the request onboard the vehicle, or take it out of its vehicle with `null`. */
  setRequestOnboard: (requestId: number, vehicleId: number | null) => void;
};

const GraphEditorContext = createContext<GraphEditorContextValue | null>(null);

export function useGraphEditor(): GraphEditorContextValue {
  const v = useContext(GraphEditorContext);
  if (!v) throw new Error("useGraphEditor must be used inside GraphEditorProvider");
  return v;
}

export function GraphEditorProvider({
  value,
  children,
}: {
  value: GraphEditorContextValue;
  children: ReactNode;
}) {
  return <GraphEditorContext.Provider value={value}>{children}</GraphEditorContext.Provider>;
}
