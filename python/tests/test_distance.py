"""
Tests for the distance cost component of the instance loader and the solution
checker: the distance matrix (``dist_filepath``) in HDF5, metres above the
16-bit range, the depot-return leg, and the guard against a distance weight
without a distance matrix.
"""
import shutil
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

import darpinstances.solution
import darpinstances.solution_checker
from darpinstances.solution_checker import Failure, SolutionChecker
from test_solution_checker import single_request_solution, write_solution

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "basic"


def make_distance_instance(root: Path, **config_overrides) -> Path:
    """
    The basic fixture with a distance matrix in HDF5: 1000 m per second of the
    travel time matrix, so the legs are above the 16-bit range.
    """
    for name in ("dm.csv", "requests.csv", "vehicles.csv"):
        shutil.copy(FIXTURE_DIR / name, root / name)
    travel_times = np.loadtxt(FIXTURE_DIR / "dm.csv", delimiter=",", dtype=np.uint32)
    with h5py.File(root / "dist.h5", "w") as dist_file:
        dist_file.create_dataset("dm", data=travel_times * 1000)
    with open(FIXTURE_DIR / "config.yaml", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    config["dist_filepath"] = "./dist.h5"
    config["cost"] = {"distance_weight": 0.001}
    config.update(config_overrides)
    config_path = root / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config, config_file)
    return config_path


def check(config_path: Path, solution_dict: dict, tmp_path: Path):
    instance, _, time_loader = darpinstances.solution_checker.load_instance(config_path)
    solution_path = write_solution(tmp_path, solution_dict)
    solution = darpinstances.solution.load_solution(solution_path, instance, time_loader)
    checker = SolutionChecker()
    ok, failures = checker.check_solution(instance, solution)
    return ok, failures, checker.last_cost


def test_distance_weight_without_dist_filepath_rejected(tmp_path):
    config_path = make_distance_instance(tmp_path)
    with open(config_path, encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    del config["dist_filepath"]
    with open(config_path, "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config, config_file)

    with pytest.raises(ValueError, match="dist_filepath"):
        darpinstances.solution_checker.load_instance(config_path)


def test_hdf_distance_matrix(tmp_path):
    config_path = make_distance_instance(tmp_path)
    # vehicle at node 0 -> pickup at node 1 (100 s, 100 000 m) -> drop-off at node 2 (200 s, 200 000 m)
    solution = single_request_solution()
    solution["cost"] = solution["plans"][0]["cost"] = 300 + 300
    solution["cost_components"] = solution["plans"][0]["cost_components"] = {"travel_time": 300, "distance": 300}

    ok, failures, cost = check(config_path, solution, tmp_path)

    assert ok, failures
    assert cost.raw["distance"] == 300_000
    assert cost.weighted["distance"] == pytest.approx(300)


def test_distance_on_depot_return_leg(tmp_path):
    config_path = make_distance_instance(tmp_path, return_to_depot=True)
    # the return leg 2 -> 0 adds 300 s and 300 000 m
    solution = single_request_solution()
    solution["cost"] = solution["plans"][0]["cost"] = 600 + 600

    ok, failures, cost = check(config_path, solution, tmp_path)

    assert ok, failures
    assert cost.raw["distance"] == 600_000


def test_wrong_distance_component_reported(tmp_path):
    config_path = make_distance_instance(tmp_path)
    solution = single_request_solution()
    solution["cost"] = solution["plans"][0]["cost"] = 600
    solution["plans"][0]["cost_components"] = {"travel_time": 300, "distance": 250}

    ok, failures, _ = check(config_path, solution, tmp_path)

    assert not ok
    assert failures[Failure.PLAN_COST_COMPONENT] == 1
