import { readdirSync, readFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020";
import { describe, expect, it } from "vitest";

const SCHEMA_URL = new URL("../../../../JSON/instance_spec.schema.json", import.meta.url);
const EXAMPLES_URL = new URL("../../examples/", import.meta.url);

const ajv = new Ajv2020({ allErrors: true, strict: true });
const validate = ajv.compile(JSON.parse(readFileSync(SCHEMA_URL, "utf8")) as object);

function errorsOf(doc: unknown): string[] {
  return validate(doc) ? [] : (validate.errors ?? []).map((e) => `${e.instancePath}: ${e.message}`);
}

describe("instance_spec.schema.json", () => {
  const examples = readdirSync(EXAMPLES_URL).filter((f) => f.endsWith(".json"));

  it("has examples", () => {
    expect(examples.length).toBeGreaterThan(0);
  });

  it.each(examples)("accepts examples/%s", (name) => {
    const doc = JSON.parse(readFileSync(new URL(name, EXAMPLES_URL), "utf8")) as unknown;
    expect(errorsOf(doc)).toEqual([]);
  });

  it("rejects a non-integer capacity", () => {
    const errors = errorsOf({
      nodes: [{ id: 0 }],
      edges: [],
      vehicles: [{ position: 0, capacity: "4" }],
    });
    expect(errors).toEqual(["/vehicles/0/capacity: must be integer"]);
  });

  it("rejects unknown properties", () => {
    const errors = errorsOf({ nodes: [{ id: 0 }], edges: [], vehicels: [] });
    expect(errors).toEqual([": must NOT have additional properties"]);
  });

  it("requires remaining_time with en_route_to", () => {
    const errors = errorsOf({
      nodes: [{ id: 0 }, { id: 1 }],
      edges: [{ from: 0, to: 1, travel_time: 10 }],
      vehicles: [{ position: 0, capacity: 1, en_route_to: 1 }],
    });
    expect(errors).toEqual(["/vehicles/0: must have property remaining_time when property en_route_to is present"]);
  });
});
