import JSZip from "jszip";
import { buildDistanceMatrix, buildNodeIndex, type ExportSolutionInput } from "./exportSolution";
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

function buildConfigYaml(problemType: ProblemType, maxDelaySeconds: number | null): string {
  // Minimal config: filepaths, and the settings that differ from the defaults.
  return [
    ...(problemType === "fleet-sizing" ? [`problem: ${problemType}`] : []),
    `demand:`,
    `  filepath: ${yamlEscapeString("./requests.csv")}`,
    // The vehicles of a fleet-sizing instance are not an input.
    ...(problemType === "DARP"
      ? [`vehicles:`, `  filepath: ${yamlEscapeString("./vehicles.csv")}`]
      : []),
    `dm_filepath: ${yamlEscapeString("./dm.csv")}`,
    ...(maxDelaySeconds !== null
      ? [`max_delay:`, `  mode: absolute`, `  seconds: ${maxDelaySeconds}`]
      : []),
    ``,
  ].join("\n");
}

/** `solutionItems` supplies the `current_plan` of each vehicle in `vehicle_data.json`. */
export type ExportInstanceInput = ExportSolutionInput & {
  /** Optional screenshot of the graph (cropped to nodes), e.g. `instance.png`. */
  pngBlob?: Blob | null;
};

export async function exportInstanceZip(input: ExportInstanceInput) {
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

  const zip = new JSZip();
  zip.file("requests.csv", reqLines.join(""));
  if (input.problemType === "DARP") {
    zip.file("vehicles.csv", vehiclesLines.join(""));
  }
  zip.file("dm.csv", dmLines.join(""));
  zip.file("config.yaml", buildConfigYaml(input.problemType, input.maxDelaySeconds));
  if (hasVehicleState(input)) {
    const vehicleData = buildVehicleDataExportObject(input, idToIndex, dm);
    zip.file("vehicle_data.json", `${JSON.stringify(vehicleData, null, 2)}\n`);
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
