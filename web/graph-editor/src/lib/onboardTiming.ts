import {
  vehicleNextLocation,
  vehicleStartNodeId,
  type RequestState,
  type RoadEdgeData,
  type VehicleState,
} from "./graphModel";

type TimingEdge = { id: string; source: string; target: string; data?: RoadEdgeData };

export type OnboardTiming = {
  /** Current time of the instance: the moment the vehicle positions on the map describe. */
  now: number;
  /** Pickup time of every onboard request (by request id). */
  pickupTimes: Map<number, number>;
  /** Onboard requests whose vehicle cannot have driven from the request origin to its position. */
  unreachable: RequestState[];
};

/**
 * Shortest driving time from the request origin to the current position of the vehicle that
 * carries it. `Infinity` if there is no such path.
 */
function minTimeSincePickup(
  request: RequestState,
  vehicle: VehicleState,
  edges: TimingEdge[],
  idToIndex: Map<string, number>,
  dm: number[][],
): number {
  const origin = idToIndex.get(request.originNodeId!)!;
  const start = idToIndex.get(vehicleStartNodeId(vehicle, edges))!;
  if (vehicle.location.kind === "node") return dm[origin][start];
  // Integer split of the edge travel time, complementary to the exported remaining time.
  const edge = edges.find((e) => e.id === (vehicle.location as { edgeId: string }).edgeId)!;
  const travelled = edge.data!.travelTime - vehicleNextLocation(vehicle, edges)!.remainingTime;
  return dm[origin][start] + travelled;
}

/**
 * Time model of an instance with onboard requests: time 0 is the pickup of the earliest picked up
 * onboard request. By default, a request is assumed to be picked up as late as possible, i.e.,
 * the vehicle drove from the request origin to its current position by the shortest path. The
 * current time is then the longest such drive over all onboard requests.
 *
 * A pickup time set by the user (`onboardPickupTimeSeconds`) is kept as is; the current time is
 * late enough for the vehicle to reach its position from that pickup.
 *
 * Without onboard requests, the current time is 0.
 */
export function computeOnboardTiming(
  vehicles: VehicleState[],
  requests: RequestState[],
  edges: TimingEdge[],
  idToIndex: Map<string, number>,
  dm: number[][],
): OnboardTiming {
  const vehiclesById = new Map(vehicles.map((v) => [v.id, v]));
  const onboard = requests
    .filter((r) => r.onboardVehicleId !== null)
    .map((request) => ({
      request,
      minTimeSincePickup: minTimeSincePickup(
        request,
        vehiclesById.get(request.onboardVehicleId!)!,
        edges,
        idToIndex,
        dm,
      ),
    }));

  const unreachable = onboard
    .filter((o) => !Number.isFinite(o.minTimeSincePickup))
    .map((o) => o.request);
  const reachable = onboard.filter((o) => Number.isFinite(o.minTimeSincePickup));

  const now = reachable.reduce(
    (latest, o) =>
      Math.max(latest, (o.request.onboardPickupTimeSeconds ?? 0) + o.minTimeSincePickup),
    0,
  );

  const pickupTimes = new Map<number, number>();
  for (const o of reachable) {
    pickupTimes.set(o.request.id, o.request.onboardPickupTimeSeconds ?? now - o.minTimeSincePickup);
  }
  return { now, pickupTimes, unreachable };
}
