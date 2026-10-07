import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { buildInstanceFiles } from "./exportInstance";
import { buildDistanceMatrix, buildNodeIndex } from "./exportSolution";
import { importInstanceFromBundle, type ImportInstanceResult } from "./importInstance";
import { buildEditorStateFromSpec, toExportInput, type InstanceSpec } from "./instanceSpec";

function example(name: string): InstanceSpec {
  return JSON.parse(
    readFileSync(new URL(`../../examples/${name}`, import.meta.url), "utf8"),
  ) as InstanceSpec;
}

function distanceMatrix(state: ImportInstanceResult): number[][] {
  return buildDistanceMatrix(state.edges, buildNodeIndex(state.nodes));
}

describe("buildInstanceFiles", () => {
  const state = buildEditorStateFromSpec(example("small-darp.json"));
  const files = buildInstanceFiles(toExportInput(state));

  it("writes the instance files of a DARP instance with vehicle state", () => {
    expect(Object.keys(files).sort()).toEqual(
      ["config.yaml", "dm.csv", "requests.csv", "vehicle_data.json", "vehicles.csv"],
    );
    expect(files["dm.csv"].split("\n")[0]).toBe("0,120,210,180");
    expect(files["dm.csv"].split("\n")[3]).toBe("180,60,150,0");
    expect(files["requests.csv"]).toBe(
      "id,origin,destination,time\n0,0,2,0\n1,1,3,0\n2,3,0,300\n",
    );
    // The en-route vehicle is listed at the source node of its edge.
    expect(files["vehicles.csv"]).toBe("position,capacity\n0,4\n1,2\n");
    expect(files["config.yaml"]).toContain("max_delay:\n  mode: absolute\n  seconds: 300");
    // Vehicle 1 picked request 1 up at node 1 and has driven 60 of the 90 s towards node 2.
    expect(files["config.yaml"]).toContain("operation_start: 60");

    const vehicleData = JSON.parse(files["vehicle_data.json"]!) as {
      vehicle_data_list: Array<Record<string, unknown>>;
    };
    expect(vehicleData.vehicle_data_list[1]).toMatchObject({
      vehicle_index: 1,
      onboard_request_indices: [1],
      next_location_index: 2,
      time_at_next_location: 30,
    });
  });

  it("round-trips through the file import", () => {
    const imported = importInstanceFromBundle(new Map(Object.entries(files)));

    expect(imported.warnings).toEqual([]);
    expect(distanceMatrix(imported)).toEqual(distanceMatrix(state));
    expect(imported.requests).toEqual(state.requests);
    expect(imported.vehicles.map((v) => [v.id, v.capacity])).toEqual(
      state.vehicles.map((v) => [v.id, v.capacity]),
    );
    expect(imported.vehicles[1].location).toEqual(state.vehicles[1].location);
    expect(imported.problemType).toBe("DARP");
    expect(imported.maxDelaySeconds).toBe(300);
    expect(imported.currentTimeSeconds).toBeNull();
  });

  it("writes no vehicles.csv for a fleet-sizing instance", () => {
    const fleet = buildInstanceFiles(toExportInput(example2()));
    expect(Object.keys(fleet).sort()).toEqual(["config.yaml", "dm.csv", "requests.csv"]);
    expect(fleet["config.yaml"]).toContain("problem: fleet-sizing");
  });
});

function example2(): ImportInstanceResult {
  return buildEditorStateFromSpec(example("fleet-sizing-no-positions.json"));
}
