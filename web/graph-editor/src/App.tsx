import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  GraphEditorProvider,
  GRAPH_EDITOR_DND_MIME,
  type SelectedVehicle,
  type SelectedRequest,
} from "./GraphEditorContext";
import { RoadEdge } from "./components/RoadEdge";
import { RoadNode, type RoadNodeType } from "./components/RoadNode";
import { VehicleGlyph } from "./components/VehicleGlyph";
import { RequestGlyph } from "./components/RequestGlyph";
import { captureCroppedFlowPng } from "./lib/captureFlowPng";
import { exportInstanceZip } from "./lib/exportInstance";
import {
  DEFAULT_TRAVEL_TIME_SECONDS,
  DEFAULT_REQUEST_PICKUP_TIME_SECONDS,
  DEFAULT_VEHICLE_CAPACITY,
  handleIdsForDirectedEdge,
  hasDirectedEdge,
  makeEdgeId,
  type RoadEdgeData,
  type RequestBadge,
  type RequestState,
} from "./lib/graphModel";
import "./App.css";

const nodeTypes = { road: RoadNode };
const edgeTypes = { road: RoadEdge };

function newRoadNode(
  id: string,
  logicalId: number,
  position: { x: number; y: number },
): RoadNodeType {
  return {
    id,
    type: "road",
    position,
    data: { logicalId, vehicles: [], requestBadges: [] },
  };
}

function roadEdge(source: string, target: string, travelTime: number): Edge<RoadEdgeData> {
  return {
    id: makeEdgeId(source, target),
    type: "road",
    source,
    target,
    data: { travelTime },
    markerEnd: { type: MarkerType.ArrowClosed, width: 20, height: 20 },
  };
}

function AppShell() {
  const [nodes, setNodes, onNodesChange] = useNodesState<RoadNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<RoadEdgeData>>([]);
  const [selectedVehicle, setSelectedVehicle] = useState<SelectedVehicle | null>(null);
  const [requests, setRequests] = useState<RequestState[]>([]);
  const [selectedRequest, setSelectedRequest] = useState<SelectedRequest | null>(null);

  const nextLogicalIdRef = useRef(0);
  const nextVehicleIdRef = useRef(0);
  const nextRequestIdRef = useRef(0);
  const flowHostRef = useRef<HTMLDivElement | null>(null);
  const rfInstanceRef = useRef<ReactFlowInstance<RoadNodeType, Edge<RoadEdgeData>> | null>(null);

  const deselectEdges = useCallback(() => {
    setEdges((eds) => eds.map((e) => ({ ...e, selected: false })));
  }, [setEdges]);

  const selectVehicle = useCallback(
    (sel: SelectedVehicle | null) => {
      setSelectedVehicle(sel);
      if (sel) deselectEdges();
      if (sel) setSelectedRequest(null);
    },
    [deselectEdges],
  );

  const selectRequest = useCallback(
    (sel: SelectedRequest | null) => {
      setSelectedRequest(sel);
      if (sel) deselectEdges();
      if (sel) setSelectedVehicle(null);
    },
    [deselectEdges],
  );

  const addVehicleToNode = useCallback(
    (nodeId: string) => {
      const vid = nextVehicleIdRef.current++;
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                data: {
                  ...n.data,
                  vehicles: [...n.data.vehicles, { id: vid, capacity: DEFAULT_VEHICLE_CAPACITY }],
                },
              }
            : n,
        ),
      );
    },
    [setNodes],
  );

  const moveVehicle = useCallback(
    (fromNodeId: string, vehicleId: number, toNodeId: string) => {
      if (fromNodeId === toNodeId) return;
      setNodes((nds) => {
        const from = nds.find((n) => n.id === fromNodeId);
        const v = from?.data.vehicles.find((x) => x.id === vehicleId);
        if (!v) return nds;
        return nds.map((n) => {
          if (n.id === fromNodeId) {
            return {
              ...n,
              data: {
                ...n.data,
                vehicles: n.data.vehicles.filter((x) => x.id !== vehicleId),
              },
            };
          }
          if (n.id === toNodeId) {
            return { ...n, data: { ...n.data, vehicles: [...n.data.vehicles, v] } };
          }
          return n;
        });
      });
      setSelectedVehicle((sel) =>
        sel?.vehicleId === vehicleId && sel.nodeId === fromNodeId
          ? { nodeId: toNodeId, vehicleId }
          : sel,
      );
    },
    [setNodes],
  );

  const setVehicleCapacity = useCallback(
    (nodeId: string, vehicleId: number, capacity: number) => {
      if (!Number.isFinite(capacity) || capacity < 0) return;
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                data: {
                  ...n.data,
                  vehicles: n.data.vehicles.map((x) =>
                    x.id === vehicleId ? { ...x, capacity } : x,
                  ),
                },
              }
            : n,
        ),
      );
    },
    [setNodes],
  );

  const removeVehicle = useCallback(
    (nodeId: string, vehicleId: number) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                data: {
                  ...n.data,
                  vehicles: n.data.vehicles.filter((v) => v.id !== vehicleId),
                },
              }
            : n,
        ),
      );
      setSelectedVehicle((sel) =>
        sel?.nodeId === nodeId && sel.vehicleId === vehicleId ? null : sel,
      );
    },
    [setNodes],
  );

  const addRequestToNode = useCallback(
    (nodeId: string) => {
      const rid = nextRequestIdRef.current++;
      setRequests((rs) => [
        ...rs,
        {
          id: rid,
          pickupTimeSeconds: DEFAULT_REQUEST_PICKUP_TIME_SECONDS,
          originNodeId: nodeId,
          destinationNodeId: null,
        },
      ]);
      setSelectedRequest({ requestId: rid });
    },
    [setRequests],
  );

  const dropRequestOnNode = useCallback(
    (requestId: number, nodeId: string) => {
      setRequests((rs) =>
        rs.map((r) => {
          if (r.id !== requestId) return r;
          // Step 1: set origin
          if (!r.originNodeId) {
            return { ...r, originNodeId: nodeId, destinationNodeId: null };
          }
          // Step 2: set destination (must differ from origin)
          if (!r.destinationNodeId) {
            if (r.originNodeId === nodeId) return r;
            return { ...r, destinationNodeId: nodeId };
          }
          // If already complete: dropping resets origin to this node and clears destination,
          // so user can pick a new destination with the next drop.
          return { ...r, originNodeId: nodeId, destinationNodeId: null };
        }),
      );
      setSelectedRequest({ requestId });
    },
    [setRequests],
  );

  const setRequestPickupTime = useCallback(
    (requestId: number, pickupTimeSeconds: number) => {
      if (!Number.isFinite(pickupTimeSeconds) || pickupTimeSeconds < 0) return;
      setRequests((rs) =>
        rs.map((r) => (r.id === requestId ? { ...r, pickupTimeSeconds } : r)),
      );
    },
    [setRequests],
  );

  const removeRequest = useCallback(
    (requestId: number) => {
      setRequests((rs) => rs.filter((r) => r.id !== requestId));
      setSelectedRequest((sel) => (sel?.requestId === requestId ? null : sel));
    },
    [setRequests],
  );

  const graphContextValue = useMemo(
    () => ({
      selectedVehicle,
      selectVehicle,
      addVehicleToNode,
      moveVehicle,
      setVehicleCapacity,
      removeVehicle,
      selectedRequest,
      selectRequest,
      addRequestToNode,
      dropRequestOnNode,
      setRequestPickupTime,
      removeRequest,
    }),
    [
      selectedVehicle,
      selectVehicle,
      addVehicleToNode,
      moveVehicle,
      setVehicleCapacity,
      removeVehicle,
      selectedRequest,
      selectRequest,
      addRequestToNode,
      dropRequestOnNode,
      setRequestPickupTime,
      removeRequest,
    ],
  );

  const addNode = useCallback(() => {
    const logicalId = nextLogicalIdRef.current++;
    const id = String(logicalId);
    setNodes((nds) => {
      const offset = nds.length * 28;
      return [
        ...nds,
        newRoadNode(id, logicalId, { x: 80 + offset, y: 120 + (offset % 140) }),
      ];
    });
  }, [setNodes]);

  const onConnect = useCallback(
    (connection: Connection) => {
      const { source, target } = connection;
      if (!source || !target || source === target) return;

      const nodeMap = new Map(nodes.map((n) => [n.id, n]));
      const ns = nodeMap.get(source);
      const nt = nodeMap.get(target);
      if (!ns || !nt) return;

      const ab = handleIdsForDirectedEdge(ns, nt);
      const ba = handleIdsForDirectedEdge(nt, ns);

      setEdges((eds) => {
        const next = [...eds];
        const pushIfMissing = (s: string, t: string, sh: string, th: string) => {
          if (!hasDirectedEdge(next, s, t)) {
            next.push({
              ...roadEdge(s, t, DEFAULT_TRAVEL_TIME_SECONDS),
              sourceHandle: sh,
              targetHandle: th,
            });
          }
        };
        pushIfMissing(source, target, ab.sourceHandle, ab.targetHandle);
        pushIfMissing(target, source, ba.sourceHandle, ba.targetHandle);
        return next;
      });
    },
    [nodes, setEdges],
  );

  useEffect(() => {
    setEdges((eds) =>
      eds.map((edge) => {
        const sn = nodes.find((n) => n.id === edge.source);
        const tn = nodes.find((n) => n.id === edge.target);
        if (!sn || !tn) return edge;
        const { sourceHandle, targetHandle } = handleIdsForDirectedEdge(sn, tn);
        if (edge.sourceHandle === sourceHandle && edge.targetHandle === targetHandle) return edge;
        return { ...edge, sourceHandle, targetHandle };
      }),
    );
  }, [nodes, setEdges]);

  useEffect(() => {
    // Derive per-node request badges for rendering chips.
    setNodes((nds) =>
      nds.map((n) => {
        const badges: RequestBadge[] = [];
        for (const r of requests) {
          if (r.originNodeId === n.id) {
            badges.push({
              id: r.id,
              pickupTimeSeconds: r.pickupTimeSeconds,
              role: "origin",
              otherNodeId: r.destinationNodeId,
            });
          } else if (r.destinationNodeId === n.id) {
            badges.push({
              id: r.id,
              pickupTimeSeconds: r.pickupTimeSeconds,
              role: "destination",
              otherNodeId: r.originNodeId,
            });
          }
        }
        // Avoid pointless state churn.
        const prev: RequestBadge[] = n.data.requestBadges;
        if (
          prev.length === badges.length &&
          prev.every(
            (p, i) =>
              p.id === badges[i]?.id &&
              p.role === badges[i]?.role &&
              p.otherNodeId === badges[i]?.otherNodeId &&
              p.pickupTimeSeconds === badges[i]?.pickupTimeSeconds,
          )
        ) {
          return n;
        }
        return { ...n, data: { ...n.data, requestBadges: badges } };
      }),
    );
  }, [requests, setNodes]);

  const onNodesDelete = useCallback(
    (deleted: RoadNodeType[]) => {
      const ids = new Set(deleted.map((n) => n.id));
      setEdges((eds) => eds.filter((e) => !ids.has(e.source) && !ids.has(e.target)));
      setSelectedVehicle((sel) => (sel && ids.has(sel.nodeId) ? null : sel));
      setRequests((rs) =>
        rs
          .map((r) => ({
            ...r,
            originNodeId: r.originNodeId && ids.has(r.originNodeId) ? null : r.originNodeId,
            destinationNodeId:
              r.destinationNodeId && ids.has(r.destinationNodeId) ? null : r.destinationNodeId,
          }))
          .filter((r) => r.originNodeId !== null || r.destinationNodeId !== null),
      );
    },
    [setEdges],
  );

  useEffect(() => {
    if (!selectedRequest) return;
    if (!requests.some((r) => r.id === selectedRequest.requestId)) {
      setSelectedRequest(null);
    }
  }, [requests, selectedRequest]);

  const onSelectionChange = useCallback(
    ({ edges: selEdges }: { edges: Edge<RoadEdgeData>[] }) => {
      if (selEdges.some((e) => e.selected)) {
        setSelectedVehicle(null);
        setSelectedRequest(null);
      }
    },
    [],
  );

  const selectedEdge = useMemo(() => edges.find((e) => e.selected), [edges]);

  const selectedVehicleRecord = useMemo(() => {
    if (!selectedVehicle) return null;
    const n = nodes.find((x) => x.id === selectedVehicle.nodeId);
    const v = n?.data.vehicles.find((x) => x.id === selectedVehicle.vehicleId);
    if (!n || !v) return null;
    return { node: n, vehicle: v };
  }, [nodes, selectedVehicle]);

  const selectedRequestRecord = useMemo(() => {
    if (!selectedRequest) return null;
    const r = requests.find((x) => x.id === selectedRequest.requestId);
    if (!r) return null;
    return r;
  }, [requests, selectedRequest]);

  const setSelectedTravelTime = useCallback(
    (raw: string) => {
      if (!selectedEdge) return;
      const n = Number(raw);
      if (!Number.isFinite(n) || n < 0) return;
      setEdges((eds) =>
        eds.map((e) =>
          e.id === selectedEdge.id ? { ...e, data: { ...e.data, travelTime: n } } : e,
        ),
      );
    },
    [selectedEdge, setEdges],
  );

  const setInspectorVehicleCapacity = useCallback(
    (raw: string) => {
      if (!selectedVehicle) return;
      const n = Number(raw);
      if (!Number.isFinite(n) || n < 0) return;
      setVehicleCapacity(selectedVehicle.nodeId, selectedVehicle.vehicleId, n);
    },
    [selectedVehicle, setVehicleCapacity],
  );

  const setInspectorRequestPickupTime = useCallback(
    (raw: string) => {
      if (!selectedRequest) return;
      const n = Number(raw);
      if (!Number.isFinite(n) || n < 0) return;
      setRequestPickupTime(selectedRequest.requestId, n);
    },
    [selectedRequest, setRequestPickupTime],
  );

  const handleExport = useCallback(async () => {
    const host = flowHostRef.current;
    const rf = rfInstanceRef.current;
    let pngBlob: Blob | null = null;
    if (host && rf && nodes.length > 0) {
      try {
        pngBlob = await captureCroppedFlowPng(host, rf, nodes);
      } catch {
        pngBlob = null;
      }
    }
    await exportInstanceZip({ nodes, edges, requests, pngBlob });
  }, [nodes, edges, requests]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, select, [contenteditable=true]")) return;
      if (edges.some((ed) => ed.selected)) return;
      if (selectedVehicle) {
        e.preventDefault();
        removeVehicle(selectedVehicle.nodeId, selectedVehicle.vehicleId);
        return;
      }
      if (selectedRequest) {
        e.preventDefault();
        removeRequest(selectedRequest.requestId);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedVehicle, selectedRequest, edges, removeVehicle, removeRequest]);

  return (
    <GraphEditorProvider value={graphContextValue}>
      <div className="app">
        <header className="app__toolbar">
          <h1 className="app__title">Road network sketcher</h1>
          <button type="button" className="app__btn" onClick={addNode}>
            Add node
          </button>
          <button type="button" className="app__btn" onClick={() => void handleExport()}>
            Export
          </button>
          <div
            className="vehicle-palette"
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData(
                GRAPH_EDITOR_DND_MIME,
                JSON.stringify({ kind: "new-vehicle" }),
              );
              e.dataTransfer.effectAllowed = "copy";
            }}
            title="Drag onto a node to park a vehicle there"
          >
            <VehicleGlyph />
            <span>Vehicle</span>
            <span className="vehicle-palette__hint">→ node</span>
          </div>
          <div
            className="request-palette"
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData(
                GRAPH_EDITOR_DND_MIME,
                JSON.stringify({ kind: "new-request" }),
              );
              e.dataTransfer.effectAllowed = "copy";
            }}
            title="Drag onto a node to set request origin. Drag the request again to set destination."
          >
            <RequestGlyph />
            <span>Request</span>
            <span className="vehicle-palette__hint">O→D</span>
          </div>
          <p className="app__hint">
            Connect nodes with handles; both directions added. Drag <strong>Vehicle</strong> onto a
            node (default capacity {DEFAULT_VEHICLE_CAPACITY}). Drag chips between nodes to relocate.
            Drag <strong>Request</strong> to set origin, then drag it again to set destination. Layout only.
          </p>
        </header>

        <div className="app__main">
          <div className="app__flow" ref={flowHostRef}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onInit={(inst) => {
                rfInstanceRef.current = inst;
              }}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodesDelete={onNodesDelete}
              onSelectionChange={onSelectionChange}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              fitView
              snapToGrid
              snapGrid={[16, 16]}
              deleteKeyCode={["Backspace", "Delete"]}
              connectionLineStyle={{ strokeWidth: 2 }}
              defaultEdgeOptions={{
              type: "road",
              style: { stroke: "#6b7280", fill: "none", strokeWidth: 2 },
            }}
            >
              <Background gap={16} />
              <Controls />
              <MiniMap pannable zoomable />
            </ReactFlow>
          </div>

          <aside className="app__inspector" aria-label="Inspector">
            {selectedVehicleRecord ? (
              <>
                <h2 className="app__inspector-title">Selected vehicle</h2>
                <p className="app__inspector-route">
                  id {selectedVehicleRecord.vehicle.id} · node {selectedVehicleRecord.node.id}
                </p>
                <label className="app__field">
                  <span>Capacity</span>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={selectedVehicleRecord.vehicle.capacity}
                    onChange={(ev) => setInspectorVehicleCapacity(ev.target.value)}
                  />
                </label>
                <p className="app__inspector-note">Delete / Backspace removes this vehicle.</p>
              </>
            ) : selectedRequestRecord ? (
              <>
                <h2 className="app__inspector-title">Selected request</h2>
                <p className="app__inspector-route">
                  R{selectedRequestRecord.id} · O:{selectedRequestRecord.originNodeId ?? "?"} · D:
                  {selectedRequestRecord.destinationNodeId ?? "?"}
                </p>
                <label className="app__field">
                  <span>Pickup time (s)</span>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={selectedRequestRecord.pickupTimeSeconds}
                    onChange={(ev) => setInspectorRequestPickupTime(ev.target.value)}
                  />
                </label>
                <p className="app__inspector-note">
                  Drag the request chip to set the missing endpoint. Delete / Backspace removes this
                  request.
                </p>
              </>
            ) : selectedEdge ? (
              <>
                <h2 className="app__inspector-title">Selected edge</h2>
                <p className="app__inspector-route">
                  {selectedEdge.source} → {selectedEdge.target}
                </p>
                <label className="app__field">
                  <span>Travel time (s)</span>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={selectedEdge.data?.travelTime ?? DEFAULT_TRAVEL_TIME_SECONDS}
                    onChange={(ev) => setSelectedTravelTime(ev.target.value)}
                  />
                </label>
              </>
            ) : (
              <p className="app__inspector-empty">
                Select an edge, vehicle chip, or request chip. Drag Vehicle/Request from the toolbar
                onto a node.
              </p>
            )}
          </aside>
        </div>
      </div>
    </GraphEditorProvider>
  );
}

export default function App() {
  return <AppShell />;
}
