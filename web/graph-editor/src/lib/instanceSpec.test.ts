import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { remainingEdgeTravelTime } from "./graphModel";
import {
  buildEditorStateFromSpec,
  DEFAULT_LAYOUT_UNIT_PX,
  InstanceSpecError,
  type InstanceSpec,
} from "./instanceSpec";

function example(name: string): InstanceSpec {
  return JSON.parse(
    readFileSync(new URL(`../../examples/${name}`, import.meta.url), "utf8"),
  ) as InstanceSpec;
}

function problemsOf(spec: InstanceSpec): string[] {
  try {
    buildEditorStateFromSpec(spec);
  } catch (e) {
    if (e instanceof InstanceSpecError) return e.problems;
    throw e;
  }
  return [];
}

const tiny: InstanceSpec = {
  nodes: [{ id: 0 }, { id: 1 }, { id: 2 }],
  edges: [
    { from: 0, to: 1, travel_time: 100, bidirectional: true },
    { from: 1, to: 2, travel_time: 50 },
  ],
  vehicles: [{ position: 0, capacity: 2 }],
  requests: [{ id: 0, origin: 0, destination: 2, time: 10 }],
};

describe("buildEditorStateFromSpec", () => {
  it("builds the editor state of the small DARP example", () => {
    const state = buildEditorStateFromSpec(example("small-darp.json"));

    expect(state.nodes.map((n) => n.id)).toEqual(["0", "1", "2", "3"]);
    expect(state.edges).toHaveLength(7);
    expect(state.edges.map((e) => e.id)).toContain("e-3-2");
    expect(state.edges.map((e) => e.id)).not.toContain("e-2-3");
    expect(state.edges.every((e) => e.sourceHandle && e.targetHandle)).toBe(true);

    expect(state.nodes[1].position).toEqual({ x: DEFAULT_LAYOUT_UNIT_PX, y: 0 });
    expect(state.nodes[3].position).toEqual({ x: DEFAULT_LAYOUT_UNIT_PX, y: DEFAULT_LAYOUT_UNIT_PX });

    expect(state.vehicles).toHaveLength(2);
    const enRoute = state.vehicles[1];
    expect(enRoute.location.kind).toBe("edge");
    if (enRoute.location.kind === "edge") {
      expect(enRoute.location.edgeId).toBe("e-1-2");
      expect(remainingEdgeTravelTime(enRoute.location.progress, 90)).toBe(30);
    }

    const onboard = state.requests.find((r) => r.id === 1)!;
    expect(onboard.onboardVehicleId).toBe(1);
    expect(onboard.onboardPickupTimeSeconds).toBeNull();

    expect(state.problemType).toBe("DARP");
    expect(state.maxDelaySeconds).toBe(300);
    expect(state.currentTimeSeconds).toBeNull();
    expect(state.nextLogicalId).toBe(4);
    expect(state.nextVehicleId).toBe(2);
    expect(state.nextRequestId).toBe(3);
    expect(state.warnings).toEqual([]);
  });

  it("lays out nodes without positions and keeps fleet-sizing settings", () => {
    const state = buildEditorStateFromSpec(example("fleet-sizing-no-positions.json"));
    expect(state.nodes).toHaveLength(5);
    const positions = new Set(state.nodes.map((n) => `${n.position.x},${n.position.y}`));
    expect(positions.size).toBe(5);
    expect(state.problemType).toBe("fleet-sizing");
    expect(state.vehicles).toEqual([]);
  });

  it("scales positions by the layout unit and snaps them to the grid", () => {
    const state = buildEditorStateFromSpec({
      ...tiny,
      nodes: [
        { id: 0, x: 0, y: 0 },
        { id: 1, x: 1, y: 0.5 },
        { id: 2, x: 2.1, y: 0 },
      ],
      settings: { layout_unit_px: 100 },
    });
    expect(state.nodes.map((n) => n.position)).toEqual([
      { x: 0, y: 0 },
      { x: 96, y: 48 },
      { x: 208, y: 0 },
    ]);
  });

  it("keeps a set pickup time and current time", () => {
    const state = buildEditorStateFromSpec({
      ...tiny,
      vehicles: [{ position: 1, capacity: 2, onboard: [{ request: 0, pickup_time: 5 }] }],
      settings: { current_time: 500 },
    });
    expect(state.requests[0].onboardPickupTimeSeconds).toBe(5);
    expect(state.currentTimeSeconds).toBe(500);
  });

  it("warns about unreachable requests and zero travel times", () => {
    const state = buildEditorStateFromSpec({
      ...tiny,
      edges: [{ from: 0, to: 1, travel_time: 0 }],
    });
    expect(state.warnings.join("\n")).toMatch(/edge 0 .*travel time is 0/);
    expect(state.warnings.join("\n")).toMatch(/request 0: destination 2 is not reachable/);
  });

  it.each<[string, InstanceSpec, RegExp]>([
    ["unknown edge node", { ...tiny, edges: [{ from: 0, to: 9, travel_time: 1 }] }, /edge 0 .*unknown node 9/],
    ["self-loop", { ...tiny, edges: [{ from: 1, to: 1, travel_time: 1 }] }, /edge 0 .*self-loop/],
    [
      "duplicate edge via bidirectional",
      { ...tiny, edges: [...tiny.edges, { from: 1, to: 0, travel_time: 7 }] },
      /edge 2 .*duplicate directed edge 1 → 0/,
    ],
    [
      "non-contiguous node ids",
      { ...tiny, nodes: [{ id: 0 }, { id: 1 }, { id: 5 }] },
      /node 5: ids must be 0\.\.2/,
    ],
    ["duplicate node id", { ...tiny, nodes: [{ id: 0 }, { id: 1 }, { id: 1 }] }, /node 1: duplicate id/],
    [
      "mixed positions",
      { ...tiny, nodes: [{ id: 0, x: 0, y: 0 }, { id: 1 }, { id: 2 }] },
      /nodes 1, 2: positions must be given for all nodes or for none/,
    ],
    ["x without y", { ...tiny, nodes: [{ id: 0, x: 0 }, { id: 1 }, { id: 2 }] }, /node 0: both x and y/],
    [
      "duplicate request id",
      { ...tiny, requests: [...tiny.requests!, { id: 0, origin: 1, destination: 2, time: 0 }] },
      /request 0: duplicate id/,
    ],
    [
      "origin equals destination",
      { ...tiny, requests: [{ id: 0, origin: 1, destination: 1, time: 0 }] },
      /request 0: origin equals destination/,
    ],
    [
      "unknown request node",
      { ...tiny, requests: [{ id: 0, origin: 1, destination: 7, time: 0 }] },
      /request 0: unknown destination node 7/,
    ],
    ["unknown vehicle position", { ...tiny, vehicles: [{ position: 3, capacity: 1 }] }, /vehicle 0: unknown position node 3/],
    [
      "missing en-route edge",
      { ...tiny, vehicles: [{ position: 2, capacity: 1, en_route_to: 1, remaining_time: 1 }] },
      /vehicle 0: no edge 2 → 1/,
    ],
    [
      "remaining time above travel time",
      { ...tiny, vehicles: [{ position: 0, capacity: 1, en_route_to: 1, remaining_time: 101 }] },
      /vehicle 0: remaining_time 101 exceeds the travel time 100/,
    ],
    [
      "unknown onboard request",
      { ...tiny, vehicles: [{ position: 0, capacity: 1, onboard: [{ request: 4 }] }] },
      /vehicle 0: unknown onboard request 4/,
    ],
    [
      "request onboard two vehicles",
      {
        ...tiny,
        vehicles: [
          { position: 0, capacity: 1, onboard: [{ request: 0 }] },
          { position: 1, capacity: 1, onboard: [{ request: 0 }] },
        ],
      },
      /vehicle 1: request 0 is already onboard vehicle 0/,
    ],
    [
      "capacity exceeded",
      {
        ...tiny,
        requests: [...tiny.requests!, { id: 1, origin: 0, destination: 1, time: 0 }],
        vehicles: [{ position: 0, capacity: 1, onboard: [{ request: 0 }, { request: 1 }] }],
      },
      /vehicle 0: 2 onboard requests exceed the capacity 1/,
    ],
    [
      "onboard request unreachable from its origin",
      {
        ...tiny,
        requests: [{ id: 0, origin: 2, destination: 0, time: 0 }],
        vehicles: [{ position: 0, capacity: 1, onboard: [{ request: 0 }] }],
      },
      /request 0: cannot be onboard vehicle 0/,
    ],
    [
      "current time too early",
      {
        ...tiny,
        vehicles: [{ position: 1, capacity: 1, onboard: [{ request: 0 }] }],
        settings: { current_time: 10 },
      },
      /settings.current_time 10 is too early.*before 100/,
    ],
  ])("rejects %s", (_name, spec, pattern) => {
    expect(problemsOf(spec).join("\n")).toMatch(pattern);
  });

  it("reports all problems at once", () => {
    const problems = problemsOf({
      ...tiny,
      edges: [{ from: 0, to: 9, travel_time: 1 }],
      vehicles: [{ position: 8, capacity: 1 }],
    });
    expect(problems).toHaveLength(2);
  });
});
