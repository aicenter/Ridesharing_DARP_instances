import type { DndPayload } from "../GraphEditorContext";

export function parseDndPayload(raw: string): DndPayload | null {
  try {
    const o = JSON.parse(raw) as unknown;
    if (!o || typeof o !== "object") return null;
    const rec = o as Record<string, unknown>;
    if (rec.kind === "new-vehicle") return { kind: "new-vehicle" };
    if (rec.kind === "new-request") return { kind: "new-request" };
    if (rec.kind === "vehicle" && typeof rec.vehicleId === "number") {
      return { kind: "vehicle", vehicleId: rec.vehicleId };
    }
    if (rec.kind === "request" && typeof rec.requestId === "number") {
      return { kind: "request", requestId: rec.requestId, fromVehicle: rec.fromVehicle === true };
    }
  } catch {
    /* ignore */
  }
  return null;
}
