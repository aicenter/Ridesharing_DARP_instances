import JSZip from "jszip";
import type { Edge } from "@xyflow/react";
import type { RoadNodeType } from "../components/RoadNode";
import type { RoadEdgeData, RequestState } from "./graphModel";

function csvRow(fields: Array<string | number>): string {
  return `${fields.join(",")}\n`;
}

function yamlEscapeString(s: string): string {
  // Minimal escaping to keep yaml readable.
  if (/^[a-zA-Z0-9_./-]+$/.test(s)) return s;
  return JSON.stringify(s);
}

function buildConfigYaml(): string {
  // Minimal config as requested: only filepaths.
  return [
    `demand:`,
    `  filepath: ${yamlEscapeString("./requests.csv")}`,
    `vehicles:`,
    `  filepath: ${yamlEscapeString("./vehicles.csv")}`,
    `dm_filepath: ${yamlEscapeString("./dm.csv")}`,
    ``,
  ].join("\n");
}

function dijkstraAllPairs(n: number, adj: Array<Array<{ to: number; w: number }>>): number[][] {
  const dm: number[][] = [];
  const unreachable = Number.POSITIVE_INFINITY;
  for (let s = 0; s < n; s++) {
    const dist = new Array<number>(n).fill(unreachable);
    const used = new Array<boolean>(n).fill(false);
    dist[s] = 0;

    for (let iter = 0; iter < n; iter++) {
      let v = -1;
      let best = unreachable;
      for (let i = 0; i < n; i++) {
        if (!used[i] && dist[i] < best) {
          best = dist[i];
          v = i;
        }
      }
      if (v === -1) break;
      used[v] = true;
      for (const e of adj[v]) {
        const nd = dist[v] + e.w;
        if (nd < dist[e.to]) dist[e.to] = nd;
      }
    }

    dm.push(dist.map((x) => (x === unreachable ? unreachable : Math.max(0, Math.round(x)))));
  }
  return dm;
}

export type ExportInstanceInput = {
  nodes: RoadNodeType[];
  edges: Edge<RoadEdgeData>[];
  requests: RequestState[];
  /** Optional screenshot of the graph (cropped to nodes), e.g. `instance.png`. */
  pngBlob?: Blob | null;
};

export async function exportInstanceZip(input: ExportInstanceInput) {
  // Export node ids as 0..n-1 by sorting by logicalId.
  const nodesSorted = [...input.nodes].sort((a, b) => a.data.logicalId - b.data.logicalId);
  const idToIndex = new Map<string, number>();
  nodesSorted.forEach((n, idx) => idToIndex.set(n.id, idx));

  const nodeCount = nodesSorted.length;
  if (nodeCount === 0) {
    throw new Error("No nodes to export.");
  }

  // Build vehicles.csv (comma-separated, with header; preferred format per README)
  const vehiclesLines: string[] = [];
  vehiclesLines.push(csvRow(["position", "capacity"]));
  const vehicles = nodesSorted.flatMap((n) =>
    n.data.vehicles.map((v) => ({ nodeId: n.id, id: v.id, capacity: v.capacity })),
  );
  vehicles.sort((a, b) => a.id - b.id);
  for (const v of vehicles) {
    const pos = idToIndex.get(v.nodeId);
    if (pos === undefined) continue;
    vehiclesLines.push(csvRow([pos, v.capacity]));
  }

  // Build requests.csv (comma-separated, with header; preferred format per README)
  // Columns: id, origin, destination, time (seconds)
  const reqLines: string[] = [];
  reqLines.push(csvRow(["id", "origin", "destination", "time"]));
  const requestsComplete = input.requests
    .filter((r) => r.originNodeId && r.destinationNodeId)
    .sort((a, b) => a.id - b.id);
  for (const r of requestsComplete) {
    const o = idToIndex.get(r.originNodeId!);
    const d = idToIndex.get(r.destinationNodeId!);
    if (o === undefined || d === undefined) continue;
    reqLines.push(csvRow([r.id, o, d, Math.round(r.pickupTimeSeconds)]));
  }

  // Build adjacency from directed edges with travelTime weights
  const adj: Array<Array<{ to: number; w: number }>> = Array.from({ length: nodeCount }, () => []);
  for (const e of input.edges) {
    const s = idToIndex.get(e.source);
    const t = idToIndex.get(e.target);
    const w = e.data?.travelTime;
    if (s === undefined || t === undefined) continue;
    if (w === undefined || !Number.isFinite(w) || w < 0) continue;
    adj[s].push({ to: t, w });
  }

  const dm = dijkstraAllPairs(nodeCount, adj);

  // dm.csv: numeric matrix, no header; unreachable pairs written as `inf`.
  const dmLines: string[] = [];
  for (let i = 0; i < nodeCount; i++) {
    dmLines.push(
      csvRow(
        dm[i].map((x) => (x === Number.POSITIVE_INFINITY ? "inf" : x)),
      ),
    );
  }

  const zip = new JSZip();
  zip.file("requests.csv", reqLines.join(""));
  zip.file("vehicles.csv", vehiclesLines.join(""));
  zip.file("dm.csv", dmLines.join(""));
  zip.file("config.yaml", buildConfigYaml());
  if (input.pngBlob) {
    zip.file("instance.png", input.pngBlob);
  }

  const blob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "instance.zip";
  a.click();
  URL.revokeObjectURL(url);
}

