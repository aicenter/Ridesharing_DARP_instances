"""
Tests for the solution checker fixes:
- max-time check no longer adds max_pickup_delay a second time (it is already
  included in the action max times on instance load),
- arrival times must exactly match the schedule recomputed from the matrix,
  unless allow_late_arrival is set, which accepts later (never earlier) arrivals,
- max_ride_time / max_route_duration are loaded from the instance config,
- dropped_requests entries are read via the schema key "index" ("id" fallback),
- action service time is read via the schema key "service_duration",
- the CLI exits non-zero on failure and prints a JSON verdict.

The fixture instance (fixtures/basic) has 4 nodes and 2 requests:
- travel times: 0->1: 100, 1->2: 200, 1->3: 60, 3->1: 60
- R0: 1 -> 2, desired pickup t=1000, min travel time 200,
      max pickup time 1120, max drop-off time 1500
- R1: 3 -> 1, desired pickup t=1100, min travel time 60,
      max pickup time 1220, max drop-off time 1460
- one vehicle at node 0 with capacity 2
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import darpinstances.solution
import darpinstances.solution_checker
from darpinstances.solution import SolutionLoader
from darpinstances.solution_checker import Failure, SolutionChecker
from darpinstances.utils import TimeLoader

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "basic"


def load_fixture(config_name: str = "config.yaml"):
    instance, _, time_loader = darpinstances.solution_checker.load_instance(FIXTURE_DIR / config_name)
    return instance, time_loader


def two_request_solution() -> dict:
    """A correct solution serving both requests with one vehicle."""
    return {
        "cost": 420,
        "plans": [
            {
                "cost": 420,
                "vehicle": {"index": 0},
                "departure_time": 900,
                "arrival_time": 1360,
                "actions": [
                    {
                        "arrival_time": 1000,
                        "departure_time": 1000,
                        "action": {
                            "id": 0, "request_index": 0, "type": "pickup",
                            "position": {"index": 1}, "min_time": 1000, "max_time": 1120,
                            "service_duration": 0,
                        },
                    },
                    {
                        "arrival_time": 1060,
                        "departure_time": 1100,
                        "action": {
                            "id": 2, "request_index": 1, "type": "pickup",
                            "position": {"index": 3}, "min_time": 1100, "max_time": 1220,
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
                        "departure_time": 1360,
                        "action": {
                            "id": 1, "request_index": 0, "type": "drop_off",
                            "position": {"index": 2}, "max_time": 1500,
                            "service_duration": 0,
                        },
                    },
                ],
            }
        ],
        "dropped_requests": [],
    }


def single_request_solution(departure_time: int = 900) -> dict:
    """A solution serving only R0 (R1 dropped); correct for departure_time=900."""
    pickup_arrival = departure_time + 100
    dropoff_arrival = pickup_arrival + 200
    return {
        "cost": 300,
        "plans": [
            {
                "cost": 300,
                "vehicle": {"index": 0},
                "departure_time": departure_time,
                "arrival_time": dropoff_arrival,
                "actions": [
                    {
                        "arrival_time": pickup_arrival,
                        "departure_time": pickup_arrival,
                        "action": {
                            "id": 0, "request_index": 0, "type": "pickup",
                            "position": {"index": 1}, "min_time": 1000, "max_time": 1120,
                            "service_duration": 0,
                        },
                    },
                    {
                        "arrival_time": dropoff_arrival,
                        "departure_time": dropoff_arrival,
                        "action": {
                            "id": 1, "request_index": 0, "type": "drop_off",
                            "position": {"index": 2}, "max_time": 1500,
                            "service_duration": 0,
                        },
                    },
                ],
            }
        ],
        "dropped_requests": [
            {"index": 1, "pickup": {"id": 2}, "drop_off": {"id": 3}, "min_travel_time": 60}
        ],
    }


def write_solution(tmp_path: Path, solution: dict, name: str = "solution.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(solution), encoding="utf-8")
    return path


def check(solution_dict: dict, tmp_path: Path, config_name: str = "config.yaml", **checker_kwargs):
    instance, time_loader = load_fixture(config_name)
    solution_path = write_solution(tmp_path, solution_dict)
    solution = darpinstances.solution.load_solution(solution_path, instance, time_loader)
    checker = SolutionChecker(**checker_kwargs)
    return checker.check_solution(instance, solution)


def test_valid_solution_passes(tmp_path):
    ok, failures = check(two_request_solution(), tmp_path)
    assert ok
    assert all(count == 0 for count in failures.values())


def test_valid_single_request_solution_passes(tmp_path):
    ok, _ = check(single_request_solution(), tmp_path)
    assert ok


def test_max_time_has_no_extra_pickup_delay_slack(tmp_path):
    # pickup at 1200 > max pickup time 1120; the old checker tolerated it because
    # it added max_pickup_delay (120) on top of the already-shifted max time
    ok, _ = check(single_request_solution(departure_time=1100), tmp_path)
    assert not ok


def test_arrival_time_mismatch_fails(tmp_path):
    # one-second deviation from the recomputed schedule; previously only warned
    solution = single_request_solution()
    actions = solution["plans"][0]["actions"]
    actions[0]["arrival_time"] = 1001  # computed: 1000
    actions[0]["departure_time"] = 1001
    actions[1]["arrival_time"] = 1201
    actions[1]["departure_time"] = 1201
    ok, failures = check(solution, tmp_path)
    assert not ok
    assert failures[Failure.ARRIVAL_TIME_MISMATCH] == 1


def late_arrival_solution() -> dict:
    """R0 served alone; the vehicle arrives at the pickup 50 s later than the direct leg
    (re-routed on the way) and the rest of the schedule continues from the real arrival.
    The extra 50 s count as driving, so the cost is 50 above the direct-leg cost."""
    solution = single_request_solution()
    actions = solution["plans"][0]["actions"]
    actions[0]["arrival_time"] = 1050  # computed: 1000
    actions[0]["departure_time"] = 1050
    actions[1]["arrival_time"] = 1250
    actions[1]["departure_time"] = 1250
    solution["plans"][0]["arrival_time"] = 1250
    solution["plans"][0]["cost"] += 50
    solution["cost"] += 50
    return solution


def test_late_arrival_rejected_by_default(tmp_path):
    ok, failures = check(late_arrival_solution(), tmp_path)
    assert not ok
    assert failures[Failure.ARRIVAL_TIME_MISMATCH] == 1


def test_late_arrival_accepted_with_flag(tmp_path):
    ok, failures = check(late_arrival_solution(), tmp_path, allow_late_arrival=True)
    assert ok
    assert all(count == 0 for count in failures.values())


def test_late_arrival_still_bounded_by_max_time(tmp_path):
    # pickup at 1150 > max pickup time 1120: the flag does not hide delays
    solution = late_arrival_solution()
    actions = solution["plans"][0]["actions"]
    actions[0]["arrival_time"] = 1150
    actions[0]["departure_time"] = 1150
    actions[1]["arrival_time"] = 1350
    actions[1]["departure_time"] = 1350
    solution["plans"][0]["arrival_time"] = 1350
    ok, failures = check(solution, tmp_path, allow_late_arrival=True)
    assert not ok
    assert failures[Failure.ARRIVAL_TIME_MISMATCH] == 0
    assert failures[Failure.MAX_TIME] == 1


def test_early_arrival_rejected_with_flag(tmp_path):
    solution = single_request_solution()
    actions = solution["plans"][0]["actions"]
    actions[1]["arrival_time"] = 1199  # computed: 1200
    actions[1]["departure_time"] = 1199
    solution["plans"][0]["arrival_time"] = 1199
    ok, failures = check(solution, tmp_path, allow_late_arrival=True)
    assert not ok
    assert failures[Failure.ARRIVAL_TIME_MISMATCH] == 1


def test_max_ride_time_loaded_from_config(tmp_path):
    # R0 rides 1000 -> 1360 = 360 s in the shared plan, above the 300 s limit;
    # previously the config value was ignored (hard-coded to 0)
    ok, _ = check(two_request_solution(), tmp_path, config_name="config_ride.yaml")
    assert not ok

    # the direct plan (ride 200 s) is fine
    ok, _ = check(single_request_solution(), tmp_path, config_name="config_ride.yaml")
    assert ok


def test_max_route_duration_loaded_from_config(tmp_path):
    # the shared plan runs 900 -> 1360 = 460 s, above the 400 s limit
    ok, _ = check(two_request_solution(), tmp_path, config_name="config_route.yaml")
    assert not ok

    # the direct plan runs 900 -> 1200 = 300 s
    ok, _ = check(single_request_solution(), tmp_path, config_name="config_route.yaml")
    assert ok


def test_dropped_requests_id_key_fallback(tmp_path):
    solution = single_request_solution()
    dropped = solution["dropped_requests"][0]
    dropped["id"] = dropped.pop("index")
    ok, _ = check(solution, tmp_path)
    assert ok


def test_action_service_duration_key():
    instance, time_loader = load_fixture()
    loader = SolutionLoader(time_loader=time_loader)
    request_map = {r.index: r for r in instance.requests}

    action = loader._load_action_from_dict(
        {"request_index": 0, "type": "pickup", "service_duration": 30}, request_map
    )
    assert action.service_time == 30

    # legacy key still accepted
    action = loader._load_action_from_dict(
        {"request_index": 0, "type": "pickup", "service_time": 25}, request_map
    )
    assert action.service_time == 25


def run_cli(solution_path: Path, config_name: str, *extra_args: str):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "darpinstances.solution_checker",
            str(solution_path),
            "-i",
            str(FIXTURE_DIR / config_name),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
    verdict = json.loads(stdout_lines[-1])
    return result.returncode, verdict


def test_cli_exit_code_and_verdict_on_valid_solution(tmp_path):
    solution_path = write_solution(tmp_path, single_request_solution())
    returncode, verdict = run_cli(solution_path, "config.yaml")
    assert returncode == 0
    assert verdict["ok"] is True
    assert verdict["plans_checked"] == 1


def test_cli_allow_late_arrival_flag(tmp_path):
    solution_path = write_solution(tmp_path, late_arrival_solution())
    returncode, verdict = run_cli(solution_path, "config.yaml")
    assert returncode == 1
    assert verdict["ok"] is False

    returncode, verdict = run_cli(solution_path, "config.yaml", "--allow-late-arrival")
    assert returncode == 0
    assert verdict["ok"] is True


def test_cli_exit_code_verdict_and_report_on_invalid_solution(tmp_path):
    solution_path = write_solution(tmp_path, single_request_solution(departure_time=1100))
    report_path = tmp_path / "report.json"
    returncode, verdict = run_cli(solution_path, "config.yaml", "--report", str(report_path))
    assert returncode == 1
    assert verdict["ok"] is False
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == verdict


def test_cli_verdict_reports_cost_breakdown(tmp_path):
    solution_path = write_solution(tmp_path, single_request_solution())
    returncode, verdict = run_cli(solution_path, "config.yaml")
    assert returncode == 0
    assert verdict["cost"]["reported"] == 300
    assert verdict["cost"]["computed"] == 300
    assert verdict["cost"]["components"]["travel_time"] == 300
    assert verdict["cost"]["components"]["vehicle_capital"] == 0


def test_fixture_solution_matches_solution_schema():
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    from referencing.jsonschema import DRAFT201909

    json_dir = Path(__file__).resolve().parents[2] / "JSON"
    schemas = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in json_dir.glob("*.schema.json")}
    registry = referencing.Registry()
    for name, schema in schemas.items():
        resource = referencing.Resource.from_contents(schema, default_specification=DRAFT201909)
        registry = registry.with_resource(schema["$id"], resource).with_resource(name, resource)
    validator = jsonschema.Draft201909Validator(schemas["solution.schema.json"], registry=registry)

    solution = two_request_solution()
    solution["cost"] = 420.5
    solution["cost_components"] = {"travel_time": 420.5}
    validator.validate(solution)

    solution["cost_components"] = {"foo": 1}
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(solution)
