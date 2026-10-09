/**
 * The instance pipeline shared by the CLI and the service: spec JSON → schema validation →
 * editor state → instance files.
 */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import Ajv2020, { type ErrorObject } from "ajv/dist/2020";
import { buildInstanceFiles, type InstanceFiles } from "../src/lib/exportInstance";
import type { ImportInstanceResult } from "../src/lib/importInstance";
import {
  buildEditorStateFromSpec,
  InstanceSpecError,
  toExportInput,
  type InstanceSpec,
} from "../src/lib/instanceSpec";

export const SCHEMA_PATH = fileURLToPath(
  new URL("../../../JSON/instance_spec.schema.json", import.meta.url),
);

export type SpecValidator = (raw: unknown) => string[];

export type ElementCounts = { nodes: number; edges: number; vehicles: number; requests: number };

export type BuildFailure = {
  ok: false;
  stage: "input" | "schema" | "semantic" | "files" | "limits";
  errors: string[];
};

export type BuildSuccess = {
  ok: true;
  state: ImportInstanceResult;
  files: InstanceFiles;
  counts: ElementCounts;
  warnings: string[];
};

export async function readSchema(): Promise<string> {
  return readFile(SCHEMA_PATH, "utf8");
}

function formatSchemaError(e: ErrorObject): string {
  const where = e.instancePath === "" ? "/" : e.instancePath;
  const extra =
    e.keyword === "additionalProperties"
      ? ` (${String((e.params as { additionalProperty?: string }).additionalProperty)})`
      : "";
  return `${where}: ${e.message ?? e.keyword}${extra}`;
}

/** Compiles the spec schema once; the returned function lists the schema violations of a spec. */
export async function loadSpecValidator(): Promise<SpecValidator> {
  const schema = JSON.parse(await readSchema()) as object;
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  const validate = ajv.compile(schema);
  return (raw) => (validate(raw) ? [] : (validate.errors ?? []).map(formatSchemaError));
}

export function elementCounts(state: ImportInstanceResult): ElementCounts {
  return {
    nodes: state.nodes.length,
    edges: state.edges.length,
    vehicles: state.vehicles.length,
    requests: state.requests.length,
  };
}

/** Validates a parsed spec and builds the editor state and the instance files from it. */
export function buildFromSpec(raw: unknown, validate: SpecValidator): BuildSuccess | BuildFailure {
  const schemaErrors = validate(raw);
  if (schemaErrors.length > 0) return { ok: false, stage: "schema", errors: schemaErrors };

  let state: ImportInstanceResult;
  try {
    state = buildEditorStateFromSpec(raw as InstanceSpec);
  } catch (e) {
    if (e instanceof InstanceSpecError) return { ok: false, stage: "semantic", errors: e.problems };
    throw e;
  }

  let files: InstanceFiles;
  try {
    files = buildInstanceFiles(toExportInput(state));
  } catch (e) {
    return { ok: false, stage: "files", errors: [e instanceof Error ? e.message : String(e)] };
  }

  return { ok: true, state, files, counts: elementCounts(state), warnings: state.warnings };
}
