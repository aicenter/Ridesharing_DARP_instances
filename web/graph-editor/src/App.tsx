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
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
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
import { importInstanceFiles } from "./lib/importInstance";
import {
  buildDistanceMatrix,
  buildNodeIndex,
  exportSolutionJsonString,
} from "./lib/exportSolution";
import { computeOnboardTiming } from "./lib/onboardTiming";
import {
  DEFAULT_TRAVEL_TIME_SECONDS,
  DEFAULT_REQUEST_PICKUP_TIME_SECONDS,
  DEFAULT_VEHICLE_CAPACITY,
  formatVehicleLocation,
  handleIdsForDirectedEdge,
  hasDirectedEdge,
  makeEdgeId,
  vehicleNextLocation,
  type ProblemType,
  type RoadEdgeData,
  type RequestBadge,
  type RequestState,
  type VehicleLocation,
  type VehicleState,
} from "./lib/graphModel";
import {
  buildInitialSolution,
  ensureVehicleColumns,
  type SolutionItems,
} from "./lib/solutionModel";
import { SolutionPanel } from "./components/SolutionPanel";
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
    data: { logicalId, requestBadges: [] },
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
  const [vehicles, setVehicles] = useState<VehicleState[]>([]);
  const [selectedVehicle, setSelectedVehicle] = useState<SelectedVehicle | null>(null);
  const [requests, setRequests] = useState<RequestState[]>([]);
  const [selectedRequest, setSelectedRequest] = useState<SelectedRequest | null>(null);
  const [problemType, setProblemType] = useState<ProblemType>("DARP");
  const [maxDelaySeconds, setMaxDelaySeconds] = useState<number | null>(null);
  const [solutionOpen, setSolutionOpen] = useState(false);
  const [solutionItems, setSolutionItems] = useState<SolutionItems | null>(null);

  const nextLogicalIdRef = useRef(0);
  const nextVehicleIdRef = useRef(0);
  const nextRequestIdRef = useRef(0);
  const flowHostRef = useRef<HTMLDivElement | null>(null);
  const rfInstanceRef = useRef<ReactFlowInstance<RoadNodeType, Edge<RoadEdgeData>> | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

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

  const addVehicle = useCallback((location: VehicleLocation) => {
    const vid = nextVehicleIdRef.current++;
    setVehicles((vs) => [...vs, { id: vid, capacity: DEFAULT_VEHICLE_CAPACITY, location }]);
  }, []);

  const moveVehicle = useCallback((vehicleId: number, location: VehicleLocation) => {
    setVehicles((vs) => vs.map((v) => (v.id === vehicleId ? { ...v, location } : v)));
  }, []);

  const setVehicleCapacity = useCallback((vehicleId: number, capacity: number) => {
    if (!Number.isFinite(capacity) || capacity < 0) return;
    setVehicles((vs) => vs.map((v) => (v.id === vehicleId ? { ...v, capacity } : v)));
  }, []);

  /** Remove the vehicles; their onboard requests stay on the map as ordinary requests. */
  const removeVehicles = useCallback((vehicleIds: Set<number>) => {
    if (vehicleIds.size === 0) return;
    setVehicles((vs) => vs.filter((v) => !vehicleIds.has(v.id)));
    setRequests((rs) =>
      rs.map((r) =>
        r.onboardVehicleId !== null && vehicleIds.has(r.onboardVehicleId)
          ? { ...r, onboardVehicleId: null, onboardPickupTimeSeconds: null }
          : r,
      ),
    );
    setSelectedVehicle((sel) => (sel && vehicleIds.has(sel.vehicleId) ? null : sel));
  }, []);

  const removeVehicle = useCallback(
    (vehicleId: number) => removeVehicles(new Set([vehicleId])),
    [removeVehicles],
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
          onboardVehicleId: null,
          onboardPickupTimeSeconds: null,
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
          // so user can pick a new destination with the next drop. Without a destination the
          // request cannot stay onboard a vehicle.
          return {
            ...r,
            originNodeId: nodeId,
            destinationNodeId: null,
            onboardVehicleId: null,
            onboardPickupTimeSeconds: null,
          };
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

  const setRequestOnboard = useCallback(
    (requestId: number, vehicleId: number | null) => {
      if (vehicleId !== null) {
        const request = requests.find((r) => r.id === requestId)!;
        const vehicle = vehicles.find((v) => v.id === vehicleId)!;
        if (!request.originNodeId || !request.destinationNodeId) {
          window.alert(
            `Set both origin and destination of request R${requestId} before putting it onboard.`,
          );
          return;
        }
        const othersOnboard = requests.filter(
          (r) => r.onboardVehicleId === vehicleId && r.id !== requestId,
        ).length;
        if (othersOnboard >= vehicle.capacity) {
          window.alert(`Vehicle ${vehicleId} is full (capacity ${vehicle.capacity}).`);
          return;
        }
      }
      // The pickup time set by the user belongs to the ride on the previous vehicle.
      setRequests((rs) =>
        rs.map((r) =>
          r.id === requestId
            ? { ...r, onboardVehicleId: vehicleId, onboardPickupTimeSeconds: null }
            : r,
        ),
      );
      setSelectedRequest({ requestId });
    },
    [requests, vehicles],
  );

  /** Set the pickup time of an onboard request, or return it to the default with `null`. */
  const setOnboardPickupTime = useCallback((requestId: number, time: number | null) => {
    if (time !== null && (!Number.isFinite(time) || time < 0)) return;
    setRequests((rs) =>
      rs.map((r) => (r.id === requestId ? { ...r, onboardPickupTimeSeconds: time } : r)),
    );
  }, []);

  const onboardTiming = useMemo(() => {
    const idToIndex = buildNodeIndex(nodes);
    return computeOnboardTiming(
      vehicles,
      requests,
      edges,
      idToIndex,
      buildDistanceMatrix(edges, idToIndex),
    );
  }, [nodes, edges, vehicles, requests]);
  const hasOnboardRequests = requests.some((r) => r.onboardVehicleId !== null);

  useEffect(() => {
    if (!solutionOpen) return;
    setSolutionItems((prev) => (prev ? ensureVehicleColumns(prev, vehicles) : prev));
  }, [vehicles, solutionOpen]);

  const graphContextValue = useMemo(
    () => ({
      vehicles,
      selectedVehicle,
      selectVehicle,
      addVehicle,
      moveVehicle,
      setVehicleCapacity,
      removeVehicle,
      requests,
      selectedRequest,
      selectRequest,
      addRequestToNode,
      dropRequestOnNode,
      setRequestPickupTime,
      removeRequest,
      setRequestOnboard,
    }),
    [
      vehicles,
      selectedVehicle,
      selectVehicle,
      addVehicle,
      moveVehicle,
      setVehicleCapacity,
      removeVehicle,
      requests,
      selectedRequest,
      selectRequest,
      addRequestToNode,
      dropRequestOnNode,
      setRequestPickupTime,
      removeRequest,
      setRequestOnboard,
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
      const deletedEdgeIds = new Set(
        edges.filter((e) => ids.has(e.source) || ids.has(e.target)).map((e) => e.id),
      );
      setEdges((eds) => eds.filter((e) => !deletedEdgeIds.has(e.id)));
      // Vehicles go with the node or edge they are on.
      removeVehicles(
        new Set(
          vehicles
            .filter((v) =>
              v.location.kind === "node"
                ? ids.has(v.location.nodeId)
                : deletedEdgeIds.has(v.location.edgeId),
            )
            .map((v) => v.id),
        ),
      );
      setRequests((rs) =>
        rs
          .map((r) => {
            const originNodeId =
              r.originNodeId && ids.has(r.originNodeId) ? null : r.originNodeId;
            const destinationNodeId =
              r.destinationNodeId && ids.has(r.destinationNodeId) ? null : r.destinationNodeId;
            return {
              ...r,
              originNodeId,
              destinationNodeId,
              // A request that lost an endpoint cannot stay onboard a vehicle.
              ...(originNodeId === null || destinationNodeId === null
                ? { onboardVehicleId: null, onboardPickupTimeSeconds: null }
                : {}),
            };
          })
          .filter((r) => r.originNodeId !== null || r.destinationNodeId !== null),
      );
    },
    [edges, vehicles, setEdges, removeVehicles],
  );

  const onEdgesDelete = useCallback(
    (deleted: Edge<RoadEdgeData>[]) => {
      const ids = new Set(deleted.map((e) => e.id));
      removeVehicles(
        new Set(
          vehicles
            .filter((v) => v.location.kind === "edge" && ids.has(v.location.edgeId))
            .map((v) => v.id),
        ),
      );
    },
    [vehicles, removeVehicles],
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
    return vehicles.find((x) => x.id === selectedVehicle.vehicleId) ?? null;
  }, [vehicles, selectedVehicle]);

  const selectedVehicleNext = selectedVehicleRecord
    ? vehicleNextLocation(selectedVehicleRecord, edges)
    : null;
  const selectedVehicleOnboard = selectedVehicleRecord
    ? requests.filter((r) => r.onboardVehicleId === selectedVehicleRecord.id)
    : [];

  const selectedRequestRecord = useMemo(() => {
    if (!selectedRequest) return null;
    const r = requests.find((x) => x.id === selectedRequest.requestId);
    if (!r) return null;
    return r;
  }, [requests, selectedRequest]);

  const selectedOnboardPickupTime = selectedRequestRecord
    ? onboardTiming.pickupTimes.get(selectedRequestRecord.id)
    : undefined;

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
      setVehicleCapacity(selectedVehicle.vehicleId, n);
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

  const handleExportSolution = useCallback(() => {
    if (!solutionItems) return;
    try {
      const json = exportSolutionJsonString({
        nodes,
        edges,
        vehicles,
        requests,
        solutionItems,
        problemType,
        maxDelaySeconds,
      });
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "solution.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  }, [nodes, edges, vehicles, requests, solutionItems, problemType, maxDelaySeconds]);

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
    try {
      await exportInstanceZip({
        nodes,
        edges,
        vehicles,
        requests,
        // The vehicle data export takes the current plans from the solution.
        solutionItems: solutionItems ?? buildInitialSolution(vehicles, requests),
        problemType,
        maxDelaySeconds,
        pngBlob,
      });
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  }, [nodes, edges, vehicles, requests, solutionItems, problemType, maxDelaySeconds]);

  const applyImportedFiles = useCallback(
    async (files: File[]) => {
      const data = await importInstanceFiles(files);
      setNodes(data.nodes);
      setEdges(data.edges);
      setVehicles(data.vehicles);
      setRequests(data.requests);
      setProblemType(data.problemType);
      setMaxDelaySeconds(data.maxDelaySeconds);
      nextLogicalIdRef.current = data.nextLogicalId;
      nextVehicleIdRef.current = data.nextVehicleId;
      nextRequestIdRef.current = data.nextRequestId;
      setSelectedVehicle(null);
      setSelectedRequest(null);
      deselectEdges();
      if (data.warnings.length > 0) {
        window.alert(data.warnings.join("\n"));
      }
      requestAnimationFrame(() => {
        rfInstanceRef.current?.fitView({ padding: 0.2, duration: 240 });
      });
    },
    [deselectEdges, setEdges, setNodes, setRequests],
  );

  const onImportFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const list = e.target.files;
      if (!list || list.length === 0) return;
      // FileList is live: clearing the input empties it, so snapshot before reset.
      const files = Array.from(list);
      e.target.value = "";
      void applyImportedFiles(files).catch((err) => {
        window.alert(err instanceof Error ? err.message : String(err));
      });
    },
    [applyImportedFiles],
  );

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, select, [contenteditable=true]")) return;
      if (edges.some((ed) => ed.selected)) return;
      if (selectedVehicle) {
        e.preventDefault();
        removeVehicle(selectedVehicle.vehicleId);
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
          <input
            ref={importInputRef}
            type="file"
            multiple
            accept=".csv,.yaml,.yml,.json,.zip,text/csv,application/json,application/zip"
            className="app__file-input"
            aria-hidden
            tabIndex={-1}
            onChange={onImportFileChange}
          />
          <button
            type="button"
            className="app__btn"
            onClick={() => importInputRef.current?.click()}
          >
            Import
          </button>
          <button
            type="button"
            className="app__btn"
            onClick={() => {
              setSolutionOpen(true);
              setSolutionItems((prev) => prev ?? buildInitialSolution(vehicles, requests));
            }}
          >
            Create solution
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
            title="Drag onto a node to park a vehicle there, or onto an edge to place it en route"
          >
            <VehicleGlyph />
            <span>Vehicle</span>
            <span className="vehicle-palette__hint">→ node / edge</span>
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
          <label className="app__setting" title="Fleet-sizing: the vehicles are not an instance input; they are exported with the vehicle data instead of vehicles.csv">
            <span>Problem</span>
            <select
              value={problemType}
              onChange={(ev) => setProblemType(ev.target.value as ProblemType)}
            >
              <option value="DARP">DARP</option>
              <option value="fleet-sizing">fleet-sizing</option>
            </select>
          </label>
          <label className="app__setting" title="Maximum delay of the requests (max_delay, absolute mode). Leave empty to not set it.">
            <span>Max delay (s)</span>
            <input
              type="number"
              min={0}
              step={1}
              value={maxDelaySeconds ?? ""}
              onChange={(ev) => {
                const n = Number(ev.target.value);
                if (ev.target.value === "") setMaxDelaySeconds(null);
                else if (Number.isFinite(n) && n >= 0) setMaxDelaySeconds(Math.round(n));
              }}
            />
          </label>
          {hasOnboardRequests ? (
            <span className="app__setting" title="Time 0 is the pickup of the earliest picked up onboard request; the current time is the moment the vehicle positions describe.">
              Current time: {onboardTiming.now}s
            </span>
          ) : null}
          <p className="app__hint">
            <strong>Import</strong> accepts several files at once (<code>dm.csv</code> required;{" "}
            <code>requests.csv</code>, <code>vehicles.csv</code>, <code>config.yaml</code>,{" "}
            <code>vehicle_data.json</code> optional) or a single <code>.zip</code>.{" "}
            Connect nodes with handles; both directions added. Drag <strong>Vehicle</strong> onto a
            node (default capacity {DEFAULT_VEHICLE_CAPACITY}) or onto an edge to place it en route.
            Drag chips between nodes and edges to relocate.
            Drag <strong>Request</strong> to set origin, then drag it again to set destination; drag
            it onto a vehicle to put it onboard. Layout only.
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
              onEdgesDelete={onEdgesDelete}
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
                  id {selectedVehicleRecord.id} · {formatVehicleLocation(selectedVehicleRecord, edges)}
                </p>
                {selectedVehicleNext ? (
                  <p className="app__inspector-route">
                    {selectedVehicleNext.remainingTime}s to node {selectedVehicleNext.nodeId}
                  </p>
                ) : null}
                {selectedVehicleOnboard.length > 0 ? (
                  <p className="app__inspector-route">
                    Onboard: {selectedVehicleOnboard.map((r) => `R${r.id}`).join(", ")}
                  </p>
                ) : null}
                <label className="app__field">
                  <span>Capacity</span>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={selectedVehicleRecord.capacity}
                    onChange={(ev) => setInspectorVehicleCapacity(ev.target.value)}
                  />
                </label>
                <p className="app__inspector-note">
                  Drop a request chip on the vehicle to put it onboard. Delete / Backspace removes
                  this vehicle.
                </p>
              </>
            ) : selectedRequestRecord ? (
              <>
                <h2 className="app__inspector-title">Selected request</h2>
                <p className="app__inspector-route">
                  R{selectedRequestRecord.id} · O:{selectedRequestRecord.originNodeId ?? "?"} · D:
                  {selectedRequestRecord.destinationNodeId ?? "?"}
                </p>
                {selectedRequestRecord.onboardVehicleId !== null ? (
                  <p className="app__inspector-route">
                    Onboard: vehicle {selectedRequestRecord.onboardVehicleId}
                    <br />
                    <button
                      type="button"
                      className="app__inspector-btn"
                      onClick={() => setRequestOnboard(selectedRequestRecord.id, null)}
                    >
                      Remove from vehicle
                    </button>
                  </p>
                ) : null}
                {selectedRequestRecord.onboardVehicleId === null ? null : selectedOnboardPickupTime ===
                  undefined ? (
                  <p className="app__inspector-note">
                    There is no path from the request origin to the vehicle, so the request cannot
                    be onboard.
                  </p>
                ) : (
                  <>
                    <label className="app__field">
                      <span>Picked up at (s)</span>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        value={selectedOnboardPickupTime}
                        onChange={(ev) =>
                          setOnboardPickupTime(selectedRequestRecord.id, Number(ev.target.value))
                        }
                      />
                    </label>
                    {selectedRequestRecord.onboardPickupTimeSeconds !== null ? (
                      <button
                        type="button"
                        className="app__inspector-btn"
                        onClick={() => setOnboardPickupTime(selectedRequestRecord.id, null)}
                      >
                        Reset to default
                      </button>
                    ) : (
                      <p className="app__inspector-note">
                        Default: the vehicle drove from the request origin by the shortest path.
                      </p>
                    )}
                  </>
                )}
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
                  Drag the request chip to set the missing endpoint, or onto a vehicle to put the
                  request onboard. Delete / Backspace removes this request.
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

          {solutionOpen && solutionItems ? (
            <SolutionPanel
              items={solutionItems}
              onItemsChange={setSolutionItems}
              vehicles={vehicles}
              requests={requests}
              edges={edges}
              onClose={() => setSolutionOpen(false)}
              onResetFromGraph={() =>
                setSolutionItems(buildInitialSolution(vehicles, requests))
              }
              onExportSolution={handleExportSolution}
            />
          ) : null}
        </div>
      </div>
    </GraphEditorProvider>
  );
}

export default function App() {
  return <AppShell />;
}
