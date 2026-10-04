import { MarkerType, type Edge } from "@xyflow/react";
import JSZip from "jszip";
import type { RoadNodeType } from "../components/RoadNode";
import { layoutImportGraph } from "./layoutImportGraph";
import {
  makeEdgeId,
  type ProblemType,
  type RoadEdgeData,
  type RequestState,
  type VehicleState,
} from "./graphModel";
import { buildDistanceMatrix, buildNodeIndex } from "./exportSolution";
import { computeOnboardTiming } from "./onboardTiming";
import { dijkstraAllPairs } from "./shortestPaths";

const DM_INF_TOKENS = new Set(["inf", "infinity", "nan", "-1"]);

function parseNumberCell(raw: string): number {
  const s = raw.trim().toLowerCase();
  if (DM_INF_TOKENS.has(s)) return Number.POSITIVE_INFINITY;
  const n = Number(raw.trim());
  if (!Number.isFinite(n)) return Number.POSITIVE_INFINITY;
  return n;
}

function splitCsvLine(line: string): string[] {
  return line.split(",").map((c) => c.trim());
}

function parseDmCsv(text: string): number[][] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  if (lines.length === 0) throw new Error("dm.csv is empty.");
  const rows = lines.map((line) => splitCsvLine(line).map(parseNumberCell));
  const n = rows.length;
  for (let i = 0; i < n; i++) {
    if (rows[i].length !== n) {
      throw new Error(`dm.csv must be square: row ${i} has ${rows[i].length} columns, expected ${n}.`);
    }
  }
  for (let i = 0; i < n; i++) {
    if (!Number.isFinite(rows[i][i]) || rows[i][i] !== 0) {
      rows[i][i] = 0;
    }
  }
  return rows;
}

type CsvTable = { header: string[]; rows: string[][] };

function parseCsvWithOptionalHeader(text: string, expectHeader: boolean): CsvTable {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  if (lines.length === 0) return { header: [], rows: [] };
  const first = splitCsvLine(lines[0]);
  if (!expectHeader) {
    return { header: [], rows: lines.map((l) => splitCsvLine(l)) };
  }
  const rows = lines.slice(1).map((l) => splitCsvLine(l));
  return { header: first, rows };
}

function colIndex(header: string[], names: string[]): number {
  const lower = header.map((h) => h.trim().toLowerCase());
  for (const name of names) {
    const idx = lower.indexOf(name.toLowerCase());
    if (idx >= 0) return idx;
  }
  return -1;
}

function impliedByOneHop(dm: number[][], i: number, j: number, eps: number): boolean {
  const dij = dm[i][j];
  if (!Number.isFinite(dij)) return true;
  for (let k = 0; k < dm.length; k++) {
    if (k === i || k === j) continue;
    const dik = dm[i][k];
    const dkj = dm[k][j];
    if (!Number.isFinite(dik) || !Number.isFinite(dkj)) continue;
    if (Math.abs(dik + dkj - dij) <= eps) return true;
  }
  return false;
}

function inferSparseEdges(dm: number[][]): Array<{ from: number; to: number; w: number }> {
  const n = dm.length;
  const edges: Array<{ from: number; to: number; w: number }> = [];
  const allInt = dm.every((row) =>
    row.every((x) => !Number.isFinite(x) || Math.abs(x - Math.round(x)) < 1e-9),
  );
  const eps = allInt ? 0.5 : 1e-3 * Math.max(1, ...dm.flatMap((r) => r.filter(Number.isFinite)));

  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i === j) continue;
      const w = dm[i][j];
      if (!Number.isFinite(w)) continue;
      if (!impliedByOneHop(dm, i, j, eps)) {
        edges.push({ from: i, to: j, w: Math.max(0, Math.round(w)) });
      }
    }
  }
  return edges;
}

function emptyAdj(n: number): Array<Array<{ to: number; w: number }>> {
  return Array.from({ length: n }, () => []);
}

function adjFromEdges(
  n: number,
  edges: Array<{ from: number; to: number; w: number }>,
): Array<Array<{ to: number; w: number }>> {
  const adj = emptyAdj(n);
  for (const e of edges) {
    if (e.from === e.to) continue;
    if (!Number.isFinite(e.w) || e.w < 0) continue;
    const list = adj[e.from];
    let found = false;
    for (const x of list) {
      if (x.to === e.to) {
        x.w = Math.min(x.w, e.w);
        found = true;
        break;
      }
    }
    if (!found) list.push({ to: e.to, w: e.w });
  }
  return adj;
}

function edgesCloseEnough(dm: number[][], dm2: number[][], tol: number): boolean {
  const n = dm.length;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const a = dm[i][j];
      const b = dm2[i][j];
      const aF = Number.isFinite(a);
      const bF = Number.isFinite(b);
      if (aF !== bF) return false;
      if (!aF) continue;
      if (Math.abs(a - b) > tol) return false;
    }
  }
  return true;
}

/**
 * Ensure Dijkstra APSP on the edge set matches `dm` (within tolerance).
 * Starts from a sparse guess, then adds/tightens arcs until distances match or we give up.
 */
function edgesMatchingDm(dm: number[][]): Array<{ from: number; to: number; w: number }> {
  const n = dm.length;
  let edges = inferSparseEdges(dm);
  const tol = 1e-3;
  const maxRounds = n * n + 8;

  for (let round = 0; round < maxRounds; round++) {
    const adj = adjFromEdges(n, edges);
    const dm2 = dijkstraAllPairs(n, adj);
    if (edgesCloseEnough(dm, dm2, tol)) return edges;

    let changed = false;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const target = dm[i][j];
        if (!Number.isFinite(target)) continue;
        const got = dm2[i][j];
        if (Number.isFinite(got) && got < target - tol) {
          throw new Error(
            `Inconsistent dm: shortest path ${i}→${j} is ${got} but matrix says ${target}.`,
          );
        }
        if (!Number.isFinite(got) || got > target + tol) {
          const w = Math.max(0, Math.round(target));
          edges = [...edges, { from: i, to: j, w }];
          changed = true;
        }
      }
    }
    if (!changed) {
      throw new Error("Could not realize dm.csv as non-negative edge lengths (repair stalled).");
    }
  }

  throw new Error("Could not realize dm.csv within iteration budget.");
}

function roadEdge(source: string, target: string, travelTime: number): Edge<RoadEdgeData> {
  return {
    id: makeEdgeId(source, target),
    type: "road",
    source,
    target,
    data: { travelTime },
    style: { stroke: "#6b7280", fill: "none", strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, width: 20, height: 20 },
  };
}

export type ImportInstanceResult = {
  nodes: RoadNodeType[];
  edges: Edge<RoadEdgeData>[];
  vehicles: VehicleState[];
  requests: RequestState[];
  problemType: ProblemType;
  maxDelaySeconds: number | null;
  nextLogicalId: number;
  nextVehicleId: number;
  nextRequestId: number;
  warnings: string[];
};

/** Basename keys, lowercased (e.g. `dm.csv`). */
export type ImportFileBundle = Map<string, string>;

function normalizeBundleKey(fileName: string): string {
  const base = fileName.split(/[/\\]/).pop() ?? fileName;
  return base.toLowerCase();
}

function bundleGet(bundle: ImportFileBundle, names: string[]): string | null {
  for (const name of names) {
    const variants = [name, name.split(/[/\\]/).pop() ?? name].map((x) => x.toLowerCase());
    for (const key of variants) {
      const text = bundle.get(key);
      if (text !== undefined) return text;
    }
  }
  return null;
}

async function filesToBundle(files: File[] | FileList): Promise<ImportFileBundle> {
  const bundle: ImportFileBundle = new Map();
  for (const f of Array.from(files)) {
    const key = normalizeBundleKey(f.name);
    if (bundle.has(key)) {
      throw new Error(`Duplicate file name in selection: "${f.name}". Pick one copy or rename.`);
    }
    bundle.set(key, await f.text());
  }
  return bundle;
}

async function zipToBundle(file: File): Promise<ImportFileBundle> {
  const zip = await JSZip.loadAsync(file);
  const bundle: ImportFileBundle = new Map();
  for (const [, entry] of Object.entries(zip.files)) {
    if (entry.dir) continue;
    const key = normalizeBundleKey(entry.name);
    if (bundle.has(key)) continue;
    bundle.set(key, await entry.async("string"));
  }
  return bundle;
}

type InstanceConfig = {
  demand?: string;
  vehicles?: string;
  dm?: string;
  problemType?: ProblemType;
  maxDelaySeconds?: number;
};

/**
 * Minimal config.yaml: resolve demand/vehicles/dm paths if non-default, the problem type, and the
 * maximum delay in seconds (`max_delay` or its deprecated aliases).
 */
function parseConfig(yamlText: string): InstanceConfig {
  const out: InstanceConfig = {};
  const lineMatch = (key: string, line: string): string | null => {
    const re = new RegExp(`^\\s*${key}\\s*:\\s*(.+?)\\s*$`);
    const m = line.match(re);
    return m ? m[1].replace(/^["']|["']$/g, "").trim() : null;
  };
  let inDemand = false;
  let inVehicles = false;
  let inMaxDelay = false;
  for (const raw of yamlText.split(/\r?\n/)) {
    const line = raw;
    if (/^\S/.test(line)) {
      inMaxDelay = /^(max_delay|max_travel_time_delay)\s*:/.test(line);
    }
    const problem = lineMatch("problem", line);
    if (problem === "DARP" || problem === "fleet-sizing") out.problemType = problem;
    const maxProlongation = lineMatch("max_prolongation", line);
    if (maxProlongation) out.maxDelaySeconds = Number(maxProlongation);
    if (inMaxDelay) {
      const seconds = lineMatch("seconds", line);
      if (seconds) out.maxDelaySeconds = Number(seconds);
    }
    if (/^\s*demand\s*:/.test(line)) {
      inDemand = true;
      inVehicles = false;
      continue;
    }
    if (/^\s*vehicles\s*:/.test(line)) {
      inVehicles = true;
      inDemand = false;
      continue;
    }
    if (/^\s*\w+\s*:/.test(line) && !line.includes("filepath")) {
      if (!/^\s+/.test(line)) {
        inDemand = false;
        inVehicles = false;
      }
    }
    const dmPath = lineMatch("dm_filepath", line);
    if (dmPath) out.dm = dmPath;
    if (inDemand) {
      const p = lineMatch("filepath", line);
      if (p) out.demand = p;
    }
    if (inVehicles) {
      const p = lineMatch("filepath", line);
      if (p) out.vehicles = p;
    }
  }
  return out;
}

/** The parts of `vehicle_data.json` (`JSON/vehicle_data_list.schema.json`) the editor reads. */
type VehicleDataJson = {
  fleet_sizing_vehicles?: Array<{ index: number; capacity: number; initial_location: number }>;
  vehicle_data_list: Array<{
    vehicle_index: number;
    onboard_request_indices?: number[];
    next_location_index?: number | null;
    time_at_next_location?: number;
    current_plan: {
      actions: Array<{
        departure_time: number;
        action: { type: "pickup" | "drop_off"; request_index: number };
      }>;
    };
  }>;
};

/**
 * Apply the vehicle states: onboard requests with the pickup times from the current plan, and
 * en-route vehicles moved from their node onto the edge towards their next location.
 */
function applyVehicleData(
  vehicleData: VehicleDataJson,
  vehicles: VehicleState[],
  requests: RequestState[],
  edges: Edge<RoadEdgeData>[],
  warnings: string[],
): void {
  for (const vd of vehicleData.vehicle_data_list) {
    const vehicle = vehicles.find((v) => v.id === vd.vehicle_index);
    if (!vehicle) {
      warnings.push(`vehicle_data.json: unknown vehicle index ${vd.vehicle_index} — skipped.`);
      continue;
    }

    for (const requestIndex of vd.onboard_request_indices ?? []) {
      const request = requests.find((r) => r.id === requestIndex);
      if (!request) {
        warnings.push(
          `vehicle_data.json: unknown onboard request ${requestIndex} of vehicle ${vehicle.id} — skipped.`,
        );
        continue;
      }
      request.onboardVehicleId = vehicle.id;
      const pickup = vd.current_plan.actions.find(
        (a) => a.action.type === "pickup" && a.action.request_index === requestIndex,
      );
      request.onboardPickupTimeSeconds = pickup ? pickup.departure_time : null;
    }

    if (vd.next_location_index === undefined || vd.next_location_index === null) continue;
    if (vehicle.location.kind !== "node") continue;
    const edge = edges.find(
      (e) =>
        vehicle.location.kind === "node" &&
        e.source === vehicle.location.nodeId &&
        e.target === String(vd.next_location_index),
    );
    if (!edge) {
      warnings.push(
        `vehicle_data.json: no edge from node ${vehicle.location.nodeId} to next location ` +
          `${vd.next_location_index} of vehicle ${vehicle.id} — vehicle left on its node.`,
      );
      continue;
    }
    const travelTime = edge.data!.travelTime;
    const progress = travelTime > 0 ? 1 - (vd.time_at_next_location ?? 0) / travelTime : 0;
    vehicle.location = {
      kind: "edge",
      edgeId: edge.id,
      progress: Math.min(1, Math.max(0, progress)),
    };
  }
}

/**
 * Load instance data from a map of lowercase basename → file text (e.g. `dm.csv`, `config.yaml`).
 */
export function importInstanceFromBundle(bundle: ImportFileBundle): ImportInstanceResult {
  const warnings: string[] = [];

  let demandNames = ["requests.csv"];
  let vehiclesNames = ["vehicles.csv"];
  let dmNames = ["dm.csv"];

  const yamlText = bundleGet(bundle, ["config.yaml", "config.yml"]);
  const config = yamlText ? parseConfig(yamlText) : {};
  if (yamlText) {
    const paths = config;
    if (paths.demand) demandNames = [paths.demand.split("/").pop() ?? paths.demand, paths.demand];
    if (paths.vehicles)
      vehiclesNames = [paths.vehicles.split("/").pop() ?? paths.vehicles, paths.vehicles];
    if (paths.dm) dmNames = [paths.dm.split("/").pop() ?? paths.dm, paths.dm];
  }

  const dmText = bundleGet(bundle, dmNames);
  if (!dmText) {
    throw new Error(
      "Need dm.csv (distance matrix). Add it to the selection, or include it under the name from config.yaml.",
    );
  }

  const dm = parseDmCsv(dmText);
  const n = dm.length;
  if (n === 0) throw new Error("dm.csv has no nodes.");

  const inferredEdges = edgesMatchingDm(dm);

  const positions = layoutImportGraph(
    n,
    inferredEdges.map((e) => ({ from: e.from, to: e.to })),
  );

  const nodes: RoadNodeType[] = [];
  for (let i = 0; i < n; i++) {
    const id = String(i);
    nodes.push({
      id,
      type: "road",
      position: positions[i] ?? { x: 48 + i * 32, y: 48 },
      data: { logicalId: i, requestBadges: [] },
    });
  }

  const edges: Edge<RoadEdgeData>[] = [];
  for (const e of inferredEdges) {
    const s = String(e.from);
    const t = String(e.to);
    edges.push(roadEdge(s, t, e.w));
  }

  const vehicleDataText = bundleGet(bundle, ["vehicle_data.json"]);
  const vehicleData = vehicleDataText ? (JSON.parse(vehicleDataText) as VehicleDataJson) : null;

  const vehicles: VehicleState[] = [];
  const vehiclesText = bundleGet(bundle, vehiclesNames);
  if (vehiclesText) {
    const tbl = parseCsvWithOptionalHeader(vehiclesText, true);
    if (tbl.rows.length === 0 && tbl.header.length >= 2) {
      warnings.push("vehicles.csv has header only — no vehicles imported.");
    } else {
      const pi = colIndex(tbl.header, ["position", "node", "loc", "location"]);
      const ci = colIndex(tbl.header, ["capacity", "cap"]);
      if (pi < 0 || ci < 0) {
        warnings.push("vehicles.csv: expected columns position, capacity — skipping vehicles.");
      } else {
        let vid = 0;
        for (const row of tbl.rows) {
          const pos = Number(row[pi]);
          const cap = Number(row[ci]);
          if (!Number.isInteger(pos) || pos < 0 || pos >= n) {
            warnings.push(`Skipping vehicle row with invalid position: ${row.join(",")}`);
            continue;
          }
          if (!Number.isFinite(cap) || cap < 0) {
            warnings.push(`Skipping vehicle row with invalid capacity: ${row.join(",")}`);
            continue;
          }
          vehicles.push({
            id: vid++,
            capacity: Math.round(cap),
            location: { kind: "node", nodeId: String(pos) },
          });
        }
      }
    }
  } else if (vehicleData?.fleet_sizing_vehicles) {
    // Fleet-sizing instances have no vehicles.csv; their vehicles come with the vehicle data.
    for (const v of vehicleData.fleet_sizing_vehicles) {
      if (!Number.isInteger(v.initial_location) || v.initial_location < 0 || v.initial_location >= n) {
        warnings.push(`Skipping fleet-sizing vehicle ${v.index} with invalid initial location.`);
        continue;
      }
      vehicles.push({
        id: v.index,
        capacity: v.capacity,
        location: { kind: "node", nodeId: String(v.initial_location) },
      });
    }
  } else {
    warnings.push("No vehicles.csv found — vehicles skipped.");
  }

  const requestsText = bundleGet(bundle, demandNames);
  const requests: RequestState[] = [];
  let maxRequestId = -1;
  if (requestsText) {
    const tbl = parseCsvWithOptionalHeader(requestsText, true);
    const idI = colIndex(tbl.header, ["id", "request_id", "rid"]);
    const oI = colIndex(tbl.header, ["origin", "o", "from", "pickup"]);
    const dI = colIndex(tbl.header, ["destination", "d", "to", "dropoff", "drop"]);
    const timeI = colIndex(tbl.header, ["time", "pickup_time", "t"]);
    if (idI < 0 || oI < 0 || dI < 0 || timeI < 0) {
      warnings.push(
        "requests.csv: expected columns id, origin, destination, time — skipping requests.",
      );
    } else {
      for (const row of tbl.rows) {
        const id = Number(row[idI]);
        const o = Number(row[oI]);
        const d = Number(row[dI]);
        const time = Number(row[timeI]);
        if (!Number.isInteger(id) || !Number.isInteger(o) || !Number.isInteger(d)) {
          warnings.push(`Skipping request row: ${row.join(",")}`);
          continue;
        }
        if (o < 0 || o >= n || d < 0 || d >= n) {
          warnings.push(`Skipping request ${id}: origin/destination out of range.`);
          continue;
        }
        if (!Number.isFinite(time) || time < 0) {
          warnings.push(`Skipping request ${id}: invalid time.`);
          continue;
        }
        requests.push({
          id,
          pickupTimeSeconds: Math.round(time),
          originNodeId: String(o),
          destinationNodeId: String(d),
          onboardVehicleId: null,
          onboardPickupTimeSeconds: null,
        });
        maxRequestId = Math.max(maxRequestId, id);
      }
    }
  } else {
    warnings.push("No requests.csv found — requests skipped.");
  }

  requests.sort((a, b) => a.id - b.id);

  if (vehicleData) {
    applyVehicleData(vehicleData, vehicles, requests, edges, warnings);

    // Pickup times that the default timing would produce anyway are not kept as user-set ones.
    const idToIndex = buildNodeIndex(nodes);
    const timing = computeOnboardTiming(
      vehicles,
      requests,
      edges,
      idToIndex,
      buildDistanceMatrix(edges, idToIndex),
    );
    const defaultTiming = computeOnboardTiming(
      vehicles,
      requests.map((r) => ({ ...r, onboardPickupTimeSeconds: null })),
      edges,
      idToIndex,
      buildDistanceMatrix(edges, idToIndex),
    );
    if (timing.now === defaultTiming.now) {
      for (const r of requests) {
        if (timing.pickupTimes.get(r.id) === defaultTiming.pickupTimes.get(r.id)) {
          r.onboardPickupTimeSeconds = null;
        }
      }
    }
  }

  return {
    nodes,
    edges,
    vehicles,
    requests,
    problemType: config.problemType ?? "DARP",
    maxDelaySeconds: config.maxDelaySeconds ?? null,
    nextLogicalId: n,
    nextVehicleId: vehicles.reduce((m, v) => Math.max(m, v.id + 1), 0),
    nextRequestId: maxRequestId + 1,
    warnings,
  };
}

/** Single exported zip (same as choosing that zip alone in a multi-file picker). */
export async function importInstanceZip(file: File): Promise<ImportInstanceResult> {
  const bundle = await zipToBundle(file);
  return importInstanceFromBundle(bundle);
}

/**
 * One or more loose files and/or a single zip. If exactly one file is `.zip`, loads the archive;
 * otherwise expects basenames like `dm.csv`, `requests.csv`, `vehicles.csv`, optional `config.yaml`
 * and `vehicle_data.json`.
 * Do not mix a `.zip` with other files in the same selection.
 */
export async function importInstanceFiles(files: FileList | File[]): Promise<ImportInstanceResult> {
  const arr = Array.from(files);
  if (arr.length === 0) throw new Error("No files selected.");
  const zips = arr.filter((f) => f.name.toLowerCase().endsWith(".zip"));
  if (zips.length > 1) {
    throw new Error("Select a single .zip archive, or individual CSV/YAML files — not multiple zips.");
  }
  if (zips.length === 1 && arr.length > 1) {
    throw new Error(
      "Either select one .zip export, or pick individual files (dm.csv, …) — not both together.",
    );
  }
  if (zips.length === 1) {
    return importInstanceZip(zips[0]);
  }
  const bundle = await filesToBundle(arr);
  return importInstanceFromBundle(bundle);
}
