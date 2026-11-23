"""
Tests for the configuration handling and the output of the speed calibration step (no database needed).
"""
from types import SimpleNamespace

import pytest
import yaml

from darpinstances.instance_generation.speed_calibration import (
    RESULT_FILENAME,
    build_speed_calibration_parameters,
    write_speed_calibration,
)


def test_defaults_and_top_level_area():
    config = SimpleNamespace(area_id=4, srid=32618)
    speed_calibration = SimpleNamespace(activated=True, demand_datasets=[2, 3])

    parameters = build_speed_calibration_parameters(config, speed_calibration)

    assert parameters == {
        "area_id": 4,
        "srid": 32618,
        "demand_datasets": [2, 3],
        "start_time": None,
        "end_time": None,
        "zone_types": None,
        "ignored_zones": None,
        "min_duration_minutes": 1.0,
        "max_duration_minutes": 180.0,
        "min_ratio": 0.5,
        "max_ratio": 10.0,
    }


def test_step_values_override_defaults():
    config = SimpleNamespace(area_id=4, srid=32618)
    speed_calibration = SimpleNamespace(
        area_id=12,
        demand_datasets=2,
        zone_types=2,
        ignored_zones=[],
        start_time="2022-04-01 00:00:00",
        max_duration_minutes=120,
        min_ratio=1,
    )

    parameters = build_speed_calibration_parameters(config, speed_calibration)

    assert parameters["area_id"] == 12
    assert parameters["demand_datasets"] == [2]
    assert parameters["zone_types"] == [2]
    assert parameters["ignored_zones"] is None
    assert parameters["start_time"] == "2022-04-01 00:00:00"
    assert parameters["max_duration_minutes"] == 120.0
    assert parameters["min_ratio"] == 1.0


@pytest.mark.parametrize(
    "config, speed_calibration, message",
    [
        (SimpleNamespace(srid=32618), SimpleNamespace(demand_datasets=[1]), "area_id"),
        (SimpleNamespace(area_id=4), SimpleNamespace(demand_datasets=[1]), "srid"),
        (SimpleNamespace(area_id=4, srid=32618), SimpleNamespace(), "demand_datasets"),
        (SimpleNamespace(area_id=4, srid=32618), SimpleNamespace(demand_datasets=[]), "demand_datasets"),
        (SimpleNamespace(area_id=4, srid=32618), SimpleNamespace(demand_datasets=[1], min_ratio=0), "min_ratio"),
        (
            SimpleNamespace(area_id=4, srid=32618),
            SimpleNamespace(demand_datasets=[1], min_duration_minutes=10, max_duration_minutes=5),
            "min_duration_minutes",
        ),
        (
            SimpleNamespace(area_id=4, srid=32618),
            SimpleNamespace(demand_datasets=[1], min_ratio=3, max_ratio=2),
            "min_ratio",
        ),
    ],
)
def test_invalid_configuration_is_rejected(config, speed_calibration, message):
    with pytest.raises(ValueError, match=message):
        build_speed_calibration_parameters(config, speed_calibration)


def test_result_file(tmp_path):
    result = {"speed_factor": 0.42, "trips_total": 10, "trips_used": 8}
    parameters = {"area_id": 4, "demand_datasets": [2, 3]}

    output_path = write_speed_calibration(result, parameters, tmp_path / "area")

    assert output_path == tmp_path / "area" / RESULT_FILENAME
    with open(output_path, encoding="utf-8") as infile:
        assert yaml.safe_load(infile) == {"result": result, "parameters": parameters}
