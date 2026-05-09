import { createContext, useContext, type ReactNode } from "react";

export const GRAPH_EDITOR_DND_MIME = "application/graph-editor";

export type DndNewVehicle = { kind: "new-vehicle" };
export type DndNewRequest = { kind: "new-request" };

export type DndMoveVehicle = {
  kind: "vehicle";
  nodeId: string;
  vehicleId: number;
};

export type DndMoveRequest = {
  kind: "request";
  requestId: number;
};

export type DndPayload = DndNewVehicle | DndMoveVehicle | DndNewRequest | DndMoveRequest;

export type SelectedVehicle = { nodeId: string; vehicleId: number };
export type SelectedRequest = { requestId: number };

export type GraphEditorContextValue = {
  selectedVehicle: SelectedVehicle | null;
  selectVehicle: (sel: SelectedVehicle | null) => void;
  addVehicleToNode: (nodeId: string) => void;
  moveVehicle: (fromNodeId: string, vehicleId: number, toNodeId: string) => void;
  setVehicleCapacity: (nodeId: string, vehicleId: number, capacity: number) => void;
  removeVehicle: (nodeId: string, vehicleId: number) => void;

  selectedRequest: SelectedRequest | null;
  selectRequest: (sel: SelectedRequest | null) => void;
  addRequestToNode: (nodeId: string) => void;
  dropRequestOnNode: (requestId: number, nodeId: string) => void;
  setRequestPickupTime: (requestId: number, pickupTimeSeconds: number) => void;
  removeRequest: (requestId: number) => void;
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
