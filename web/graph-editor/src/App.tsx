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
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useMemo, useRef } from "react";
import { RoadEdge } from "./components/RoadEdge";
import { RoadNode, type RoadNodeType } from "./components/RoadNode";
import {
  DEFAULT_TRAVEL_TIME_SECONDS,
  handleIdsForDirectedEdge,
  hasDirectedEdge,
  makeEdgeId,
  type RoadEdgeData,
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
    data: { logicalId },
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

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<RoadNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<RoadEdgeData>>([]);

  const nextLogicalIdRef = useRef(0);

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

  const onNodeDragStop = useCallback(
    (_event: unknown, _node: RoadNodeType, allNodes: RoadNodeType[]) => {
      const map = new Map(allNodes.map((n) => [n.id, n]));
      setEdges((eds) =>
        eds.map((edge) => {
          const sn = map.get(edge.source);
          const tn = map.get(edge.target);
          if (!sn || !tn) return edge;
          const { sourceHandle, targetHandle } = handleIdsForDirectedEdge(sn, tn);
          return { ...edge, sourceHandle, targetHandle };
        }),
      );
    },
    [setEdges],
  );

  const onNodesDelete = useCallback(
    (deleted: RoadNodeType[]) => {
      const ids = new Set(deleted.map((n) => n.id));
      setEdges((eds) => eds.filter((e) => !ids.has(e.source) && !ids.has(e.target)));
    },
    [setEdges],
  );

  const selectedEdge = useMemo(() => edges.find((e) => e.selected), [edges]);

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

  return (
    <div className="app">
      <header className="app__toolbar">
        <h1 className="app__title">Road network sketcher</h1>
        <button type="button" className="app__btn" onClick={addNode}>
          Add node
        </button>
        <p className="app__hint">
          Connect any two nodes (handles snap to the best side toward the other node). New links add
          both directions. Delete / Backspace removes selection. Node positions are layout only.
        </p>
      </header>

      <div className="app__main">
        <div className="app__flow">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeDragStop={onNodeDragStop}
            onNodesDelete={onNodesDelete}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            snapToGrid
            snapGrid={[16, 16]}
            deleteKeyCode={["Backspace", "Delete"]}
            connectionLineStyle={{ strokeWidth: 2 }}
            defaultEdgeOptions={{ type: "road", style: { strokeWidth: 2 } }}
          >
            <Background gap={16} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>

        <aside className="app__inspector" aria-label="Edge inspector">
          {selectedEdge ? (
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
            <p className="app__inspector-empty">Select an edge to edit travel time.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
