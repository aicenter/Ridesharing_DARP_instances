import { buildVehiclePlans, type ExportSolutionInput } from "./exportSolution";

/**
 * True if the editor holds vehicle state that the static instance files cannot express. The
 * vehicles of a fleet-sizing instance belong there too, as such an instance has no vehicles file.
 */
export function hasVehicleState(
  input: Pick<ExportSolutionInput, "vehicles" | "requests" | "problemType">,
): boolean {
  return (
    input.vehicles.some((v) => v.location.kind === "edge") ||
    input.requests.some((r) => r.onboardVehicleId !== null) ||
    (input.problemType === "fleet-sizing" && input.vehicles.length > 0)
  );
}

/**
 * Build a JSON object matching `JSON/vehicle_data_list.schema.json`: the state of every vehicle
 * (onboard requests, next location of en-route vehicles) with its plan from the solution as
 * `current_plan`. Times follow the model of `computeOnboardTiming`.
 */
export function buildVehicleDataExportObject(
  input: ExportSolutionInput,
  idToIndex: Map<string, number>,
  dm: number[][],
): Record<string, unknown> {
  const vehiclePlans = buildVehiclePlans(input, { idToIndex, dm });

  return {
    ...(input.problemType === "fleet-sizing"
      ? {
          fleet_sizing_vehicles: vehiclePlans.map((p) => ({
            index: p.fleetIndex,
            capacity: p.vehicle.capacity,
            initial_location: p.initNodeIndex,
          })),
        }
      : {}),
    vehicle_data_list: vehiclePlans.map((p) => ({
      vehicle_index: p.fleetIndex,
      actual_plan_departure_time: p.plan.departure_time,
      // the node the vehicle last departed from: the source of its edge, or the node it stands at
      from_location_index: p.initNodeIndex,
      onboard_request_indices: p.onboardRequests.map((r) => r.id),
      ...(p.nextLocation
        ? {
            next_location_index: p.nextLocation.nodeIndex,
            time_at_next_location: p.nextLocation.remainingTime,
          }
        : {}),
      current_plan: p.plan,
    })),
  };
}
