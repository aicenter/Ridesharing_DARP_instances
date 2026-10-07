import JSZip from "jszip";
import {
  buildDistanceMatrix,
  buildNodeIndex,
  resolveOnboardTiming,
  type ExportSolutionInput,
} from "./exportSolution";
import { buildVehicleDataExportObject, hasVehicleState } from "./exportVehicleData";
import { vehicleStartNodeId, type ProblemType } from "./graphModel";

function csvRow(fields: Array<string | number>): string {
  return `${fields.join(",")}\n`;
}

function yamlEscapeString(s: string): string {
  // Minimal escaping to keep yaml readable.
  if (/^[a-zA-Z0-9_./-]+$/.test(s)) return s;
  return JSON.stringify(s);
}

/** @param currentTime written as the operation start of the vehicles: they cannot act before it */
function buildConfigYaml(
  problemType: ProblemType,
  maxDelaySeconds: number | null,
  currentTime: number,
): string {
  // The vehicles of a fleet-sizing instance are not an input.
  const vehiclesSection = [
    ...(problemType === "DARP" ? [`  filepath: ${yamlEscapeString("./vehicles.csv")}`] : []),
    ...(currentTime > 0 ? [`  operation_start: ${currentTime}`] : []),
  ];
  // Minimal config: filepaths, and the settings that differ from the defaults.
  return [
    ...(problemType === "fleet-sizing" ? [`problem: ${problemType}`] : []),
    `demand:`,
    `  filepath: ${yamlEscapeString("./requests.csv")}`,
    ...(vehiclesSection.length > 0 ? [`vehicles:`, ...vehiclesSection] : []),
    `dm_filepath: ${yamlEscapeString("./dm.csv")}`,
    ...(maxDelaySeconds !== null
      ? [`max_delay:`, `  mode: absolute`, `  seconds: ${maxDelaySeconds}`]
      : []),
    ``,
  ].join("\n");
}

/** Contents of the instance files by file name. */
export type InstanceFiles = {
  "config.yaml": string;
  "requests.csv": string;
  "dm.csv": string;
  /** Absent for a fleet-sizing instance: its vehicles are not an input. */
  "vehicles.csv"?: string;
  /** Present if the editor holds vehicle state, see `hasVehicleState`. */
  "vehicle_data.json"?: string;
};

/**
 * Build the instance files from the editor state; throws if the state is not consistent (see
 * `resolveOnboardTiming`). The `solutionItems` supply the `current_plan` of each vehicle in
 * `vehicle_data.json`.
 */
export function buildInstanceFiles(input: ExportSolutionInput): InstanceFiles {
  const idToIndex = buildNodeIndex(input.nodes);

  const nodeCount = idToIndex.size;
  if (nodeCount === 0) {
    throw new Error("No nodes to export.");
  }

  // Build vehicles.csv (comma-separated, with header; preferred format per README)
  // An en-route vehicle is listed at the source node of its edge.
  const vehiclesLines: string[] = [];
  vehiclesLines.push(csvRow(["position", "capacity"]));
  const vehicles = [...input.vehicles].sort((a, b) => a.id - b.id);
  for (const v of vehicles) {
    const pos = idToIndex.get(vehicleStartNodeId(v, input.edges));
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

  const dm = buildDistanceMatrix(input.edges, idToIndex);

  // dm.csv: numeric matrix, no header; unreachable pairs written as `inf`.
  const dmLines: string[] = [];
  for (let i = 0; i < nodeCount; i++) {
    dmLines.push(
      csvRow(
        dm[i].map((x) => (x === Number.POSITIVE_INFINITY ? "inf" : x)),
      ),
    );
  }

  const timing = resolveOnboardTiming(input, { idToIndex, dm });
  const files: InstanceFiles = {
    "config.yaml": buildConfigYaml(input.problemType, input.maxDelaySeconds, timing.now),
    "requests.csv": reqLines.join(""),
    "dm.csv": dmLines.join(""),
  };
  if (input.problemType === "DARP") {
    files["vehicles.csv"] = vehiclesLines.join("");
  }
  if (hasVehicleState(input)) {
    const vehicleData = buildVehicleDataExportObject(input, idToIndex, dm);
    files["vehicle_data.json"] = `${JSON.stringify(vehicleData, null, 2)}\n`;
  }
  return files;
}

export type ExportInstanceInput = ExportSolutionInput & {
  /** Optional screenshot of the graph (cropped to nodes), e.g. `instance.png`. */
  pngBlob?: Blob | null;
};

/** Download the instance files (and the screenshot, if any) as `instance.zip`. */
export async function exportInstanceZip(input: ExportInstanceInput) {
  const files = buildInstanceFiles(input);

  const zip = new JSZip();
  for (const [name, text] of Object.entries(files)) {
    zip.file(name, text);
  }
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
