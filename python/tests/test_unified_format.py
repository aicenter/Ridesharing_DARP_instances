"""
Tests for the unified instance format and the generalized solution checker:
multi-seat demand (seats / wheelchair slots / child seats), named vehicle
equipment, exclusive rides, per-request constraint overrides (inherit /
override / disabled), boarding-anchored max_travel_delay, required arrival
times with the symmetric earliness bound, per-vehicle driver rules and
operation windows, per-vehicle return_to_depot, service times, and the
generalized weighted cost model.

The extended fixture (fixtures/extended) has the same 4-node matrix as the
basic fixture and 2 requests:
- R0: 1 -> 2, t=1000, min_tt 200, service 10 s, 1 adult + 1 child-in-seat,
      requires 'ramp', required arrival 1600, walks 50/80 m
- R1: 3 -> 1, t=1100, min_tt 60, 1 adult + 1 wheelchair passenger,
      per-request max_pickup_delay override 60 s
- vehicle 0 at node 0: one seating configuration {standard: 3, wheelchair: 1},
  1 child seat, ramp, operation [800, 2000], max drive 600 s, max continuous
  drive 400 s, min pause 30 s, no depot return

Onboard slot loads along the valid schedule: after P0 {standard: 2} (adult +
child-in-seat), after P1 {standard: 3, wheelchair: 1}, after D1 {standard: 2}.

Hand-computed valid schedule (departure 900):
  P0 arr 1000 dep 1010 (service 10), P1 arr 1070 dep 1100 (wait, pause reset),
  D1 arr 1160 dep 1160, D0 arr 1360 dep 1370
Cost = 420 travel + 0.01*4200 dist + 0.5*820 ride + 0.2*320 delay
     + 0.1*240 earliness + 0.05*470 duration + 10 fixed + 25 capital = 1018.5
"""
import copy
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml

import darpinstances.solution
import darpinstances.solution_checker
from darpinstances.solution_checker import Failure, SolutionChecker

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "extended"


def valid_solution() -> dict:
    return {
        "cost": 1018,
        "plans": [
            {
                "cost": 1018,
                "vehicle": {"index": 0},
                "departure_time": 900,
                "arrival_time": 1370,
                "actions": [
                    {
                        "arrival_time": 1000,
                        "departure_time": 1010,
                        "action": {
                            "id": 0, "request_index": 0, "type": "pickup",
                            "position": {"index": 1}, "min_time": 1000, "max_time": 1120,
                            "service_duration": 10,
                        },
                    },
                    {
                        "arrival_time": 1070,
                        "departure_time": 1100,
                        "action": {
                            "id": 2, "request_index": 1, "type": "pickup",
                            "position": {"index": 3}, "min_time": 1100, "max_time": 1160,
                            "service_duration": 0,
                        },
                    },
                    {
                        "arrival_time": 1160,
                        "departure_time": 1160,
                        "action": {
                            "id": 3, "request_index": 1, "type": "drop_off",
                            "position": {"index": 1}, "max_time": 1460,
                            "service_duration": 0,
                        },
                    },
                    {
                        "arrival_time": 1360,
                        "departure_time": 1370,
                        "action": {
                            "id": 1, "request_index": 0, "type": "drop_off",
                            "position": {"index": 2}, "max_time": 1500,
                            "service_duration": 10,
                        },
                    },
                ],
            }
        ],
        "dropped_requests": [],
    }


@pytest.fixture
def instance_dir(tmp_path) -> Path:
    """A modifiable copy of the extended fixture instance."""
    target = tmp_path / "instance"
    shutil.copytree(FIXTURE_DIR, target)
    return target


def patch_request(instance_dir: Path, request_id: int, field: str, value):
    requests_path = instance_dir / "requests.csv"
    data = pd.read_csv(requests_path)
    data.loc[data["id"] == request_id, field] = value
    data.to_csv(requests_path, index=False)


def patch_vehicle(instance_dir: Path, field: str, value):
    vehicles_path = instance_dir / "vehicles.json"
    vehicles = json.loads(vehicles_path.read_text(encoding="utf-8"))
    vehicles[0][field] = value
    vehicles_path.write_text(json.dumps(vehicles), encoding="utf-8")


def patch_config(instance_dir: Path, field: str, value):
    config_path = instance_dir / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config[field] = value
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")


def check(instance_dir: Path, solution_dict: dict):
    instance, _, time_loader = darpinstances.solution_checker.load_instance(instance_dir / "config.yaml")
    solution_path = instance_dir / "solution.json"
    solution_path.write_text(json.dumps(solution_dict), encoding="utf-8")
    solution = darpinstances.solution.load_solution(solution_path, instance, time_loader)
    checker = SolutionChecker(max_error_count=1000)
    return checker.check_solution(instance, solution)


def test_extended_valid_solution_passes(instance_dir):
    ok, failures = check(instance_dir, valid_solution())
    assert ok, {failure.name: count for failure, count in failures.items() if count}


def test_relative_max_delay_mode(instance_dir):
    # delay = 1.5 * min_travel_time: R0 300 s (same windows as absolute),
    # R1 90 s (drop-off window 1250, still met at 1160)
    patch_config(instance_dir, "max_delay", {"mode": "relative", "relative": 1.5})
    ok, failures = check(instance_dir, valid_solution())
    assert ok, {failure.name: count for failure, count in failures.items() if count}


def test_seat_capacity_with_composite_passengers(instance_dir):
    # R0 needs 2 standard slots (adult + child-in-seat), R1 one more: 3 > 2
    patch_vehicle(instance_dir, "configurations", [{"standard": 2, "wheelchair": 1}])
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.CAPACITY] >= 1


def test_wheelchair_capacity(instance_dir):
    # no configuration offers a wheelchair slot
    patch_vehicle(instance_dir, "configurations", [{"standard": 3}])
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.CAPACITY] >= 1


def test_reconfiguration_between_stops(instance_dir):
    # neither configuration alone covers the whole plan: {standard: 4} fits the
    # load after P0 but has no wheelchair slot, {standard: 3, wheelchair: 1}
    # fits the load after P1. Per-stop fitting accepts the schedule — the
    # configurations model shared spots, so the active one may change
    # mid-operation.
    patch_vehicle(instance_dir, "configurations", [{"standard": 4}, {"standard": 3, "wheelchair": 1}])
    ok, failures = check(instance_dir, valid_solution())
    assert ok, {failure.name: count for failure, count in failures.items() if count}


def test_reconfiguration_no_single_fit_rejected(instance_dir):
    # after P1 the load is {standard: 3, wheelchair: 1}: {standard: 4} has no
    # wheelchair slot and {standard: 2, wheelchair: 1} lacks a standard seat —
    # the union of configurations must NOT be treated as one big vehicle
    patch_vehicle(instance_dir, "configurations", [{"standard": 4}, {"standard": 2, "wheelchair": 1}])
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.CAPACITY] >= 1


def test_capacity_sugar(instance_dir):
    # plain "capacity": N is sugar for one all-standard configuration; R1's
    # wheelchair passenger is made a standard one so the schedule fits
    patch_request(instance_dir, 1, "passengers_wheelchair", 0)
    patch_request(instance_dir, 1, "passengers_standard", 2)
    vehicles_path = instance_dir / "vehicles.json"
    vehicles = json.loads(vehicles_path.read_text(encoding="utf-8"))
    del vehicles[0]["configurations"]
    vehicles[0]["capacity"] = 4
    vehicles_path.write_text(json.dumps(vehicles), encoding="utf-8")
    ok, failures = check(instance_dir, valid_solution())
    assert ok, {failure.name: count for failure, count in failures.items() if count}


def test_child_seat_capacity(instance_dir):
    patch_vehicle(instance_dir, "child_seats", 0)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.CHILD_SEAT_CAPACITY] >= 1


def test_named_equipment(instance_dir):
    patch_vehicle(instance_dir, "equipment", [])
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.EQUIPMENT] >= 1


def test_exclusive_ride(instance_dir):
    # R1 becomes exclusive but is picked up while R0 is onboard
    patch_request(instance_dir, 1, "exclusive", 1)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.EXCLUSIVE_RIDE] >= 1


def test_max_travel_delay_boarding_anchored(instance_dir):
    # idle the vehicle at D1 so R0's ride grows to 490 s: boarding-anchored
    # delay 290 s exceeds the 280 s limit, while the requested-time-anchored
    # drop-off window (1500) is still met exactly at arrival 1500
    solution = valid_solution()
    actions = solution["plans"][0]["actions"]
    actions[2]["departure_time"] = 1300
    actions[3]["arrival_time"] = 1500
    actions[3]["departure_time"] = 1510
    solution["plans"][0]["arrival_time"] = 1510
    ok, failures = check(instance_dir, solution)
    assert not ok
    assert failures[Failure.MAX_TRAVEL_DELAY] >= 1
    assert failures[Failure.MAX_TIME] == 0


def test_max_ride_time_per_request_override(instance_dir):
    # R0 rides 350 s; the per-request override tightens the 500 s baseline
    patch_request(instance_dir, 0, "max_ride_time", 300)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.MAX_RIDE_TIME] >= 1


def test_constraint_disabled_by_override(instance_dir):
    # tightened baseline fails the solution ...
    patch_config(instance_dir, "max_ride_time", 300)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.MAX_RIDE_TIME] >= 1

    # ... but a per-request -1 disables the constraint for R0 entirely
    patch_request(instance_dir, 0, "max_ride_time", -1)
    ok, failures = check(instance_dir, valid_solution())
    assert ok, {failure.name: count for failure, count in failures.items() if count}


def test_arrival_deadline(instance_dir):
    patch_request(instance_dir, 0, "required_arrival_time", 1300)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.ARRIVAL_DEADLINE] >= 1


def test_arrival_too_early(instance_dir):
    # earliness 1700 - 1360 = 340 s exceeds the 280 s travel delay budget
    patch_request(instance_dir, 0, "required_arrival_time", 1700)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.ARRIVAL_TOO_EARLY] >= 1


def test_max_walking_distance(instance_dir):
    patch_request(instance_dir, 0, "walk_to_origin_m", 150)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.MAX_WALKING_DISTANCE] >= 1

    # disabling the constraint for the request accepts the same walk
    patch_request(instance_dir, 0, "max_walking_distance", -1)
    ok, failures = check(instance_dir, valid_solution())
    assert ok, {failure.name: count for failure, count in failures.items() if count}


def test_continuous_drive_limit(instance_dir):
    # continuous drive reaches 260 s after the pause reset at P1
    patch_vehicle(instance_dir, "max_drive_time_without_pause", 250)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.DRIVER_PAUSE] >= 1


def test_total_drive_limit(instance_dir):
    # total drive is 420 s
    patch_vehicle(instance_dir, "max_drive_time", 400)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.MAX_DRIVE_TIME] >= 1


def test_per_stop_operation_window(instance_dir):
    # the last departure (1370) violates the shortened window even though
    # every other stop fits
    patch_vehicle(instance_dir, "operation_end", 1350)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.OPERATION_WINDOW] >= 1


def test_return_to_depot_leg_checked(instance_dir):
    # depot return adds 300 s of travel: arrival 1670 violates the window
    patch_vehicle(instance_dir, "return_to_depot", True)
    patch_vehicle(instance_dir, "operation_end", 1400)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.OPERATION_WINDOW] >= 1


def test_required_vehicle(instance_dir):
    patch_request(instance_dir, 0, "required_vehicle_id", 1)
    ok, failures = check(instance_dir, valid_solution())
    assert not ok
    assert failures[Failure.REQUIRED_VEHICLE] >= 1


def test_service_time_enforced(instance_dir):
    # departing P0 at 1005 ignores the 10 s service time (earliest 1010)
    solution = valid_solution()
    solution["plans"][0]["actions"][0]["departure_time"] = 1005
    ok, failures = check(instance_dir, solution)
    assert not ok
    assert failures[Failure.DEPARTURE_TIME] >= 1


def test_generalized_cost_check(instance_dir):
    solution = valid_solution()
    solution["plans"][0]["cost"] = 900
    ok, failures = check(instance_dir, solution)
    assert not ok
    assert failures[Failure.PLAN_COST] >= 1


# ---------------------------------------------------------------- dynamic DARP


def load_requests(instance_dir: Path):
    instance, _, _ = darpinstances.solution_checker.load_instance(instance_dir / "config.yaml")
    return instance.requests


def test_request_time_column_is_loaded(instance_dir):
    from datetime import datetime, timezone

    patch_request(instance_dir, 0, "request_time", 940)
    requests = load_requests(instance_dir)
    assert requests[0].request_time == datetime.fromtimestamp(940, tz=timezone.utc)
    assert requests[1].request_time is None  # empty cell = absent


def test_request_time_absent_column_defaults_to_none(instance_dir):
    requests = load_requests(instance_dir)
    assert requests[0].request_time is None


def test_pure_deadline_request_derives_earliest_pickup(instance_dir):
    from datetime import datetime, timezone

    # R0: required arrival 1600, min travel time 200, service 10 —
    # derived earliest pickup = 1600 - 200 - 10 = 1390
    patch_request(instance_dir, 0, "time", None)
    requests = load_requests(instance_dir)
    assert requests[0].pickup_action.min_time == datetime.fromtimestamp(1390, tz=timezone.utc)


def test_request_time_floors_the_derived_earliest_pickup(instance_dir):
    from datetime import datetime, timezone

    # derived 1390, but the request only entered the system at 1450
    patch_request(instance_dir, 0, "time", None)
    patch_request(instance_dir, 0, "request_time", 1450)
    requests = load_requests(instance_dir)
    assert requests[0].pickup_action.min_time == datetime.fromtimestamp(1450, tz=timezone.utc)


def test_empty_time_without_deadline_is_rejected(instance_dir):
    # R1 has no required_arrival_time — an empty time cell is invalid
    patch_request(instance_dir, 1, "time", None)
    with pytest.raises(ValueError, match="required_arrival_time"):
        load_requests(instance_dir)
