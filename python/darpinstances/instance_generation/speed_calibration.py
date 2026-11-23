"""
Calibration of the speed factor of an area (the ``speed_calibration`` pipeline step).

The factor is the multiplier of the posted edge speeds (Road Graph Tool ``dm_generator.speed_factor``) with which the
travel times on the road network match the recorded trip durations of the demand in total. It is computed in the
database by the SQL function ``compute_speed_factor``.
"""
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import sqlalchemy
import yaml

RESULT_FILENAME = "speed_calibration.yaml"

# config key: default
_LIMIT_DEFAULTS = {
    "min_duration_minutes": 1,
    "max_duration_minutes": 180,
    "min_ratio": 0.5,
    "max_ratio": 10,
}


def _to_optional_int_list(value) -> Optional[List[int]]:
    if value is None:
        return None
    if isinstance(value, int):
        return [value]
    values = [int(item) for item in value]
    if len(values) == 0:
        return None
    return values


def build_speed_calibration_parameters(config: SimpleNamespace, speed_calibration: SimpleNamespace) -> Dict[str, Any]:
    """
    Parameters of the SQL function ``compute_speed_factor`` from the pipeline config.

    :param config: the whole pipeline config (top-level ``area_id`` and ``srid``)
    :param speed_calibration: the ``speed_calibration`` section of the config
    """
    area_id = getattr(speed_calibration, "area_id", None)
    if area_id is None:
        area_id = getattr(config, "area_id", None)
    if area_id is None:
        raise ValueError(
            "speed_calibration is activated but area_id is not set: "
            "configure speed_calibration.area_id or top-level area_id."
        )

    srid = getattr(config, "srid", None)
    if srid is None:
        raise ValueError("speed_calibration is activated but the top-level srid is not set.")

    demand_datasets = _to_optional_int_list(getattr(speed_calibration, "demand_datasets", None))
    if demand_datasets is None:
        raise ValueError("speed_calibration is activated but missing required field: demand_datasets")

    parameters = {
        "area_id": int(area_id),
        "srid": int(srid),
        "demand_datasets": demand_datasets,
        "start_time": getattr(speed_calibration, "start_time", None),
        "end_time": getattr(speed_calibration, "end_time", None),
        "zone_types": _to_optional_int_list(getattr(speed_calibration, "zone_types", None)),
        "ignored_zones": _to_optional_int_list(getattr(speed_calibration, "ignored_zones", None)),
    }
    for key, default in _LIMIT_DEFAULTS.items():
        value = float(getattr(speed_calibration, key, default))
        if value <= 0:
            raise ValueError(f"speed_calibration.{key} must be positive, got {value}")
        parameters[key] = value
    if parameters["min_duration_minutes"] > parameters["max_duration_minutes"]:
        raise ValueError("speed_calibration.min_duration_minutes must not exceed max_duration_minutes")
    if parameters["min_ratio"] > parameters["max_ratio"]:
        raise ValueError("speed_calibration.min_ratio must not exceed max_ratio")
    return parameters


def compute_speed_factor(parameters: Dict[str, Any], schema: str = "public") -> Dict[str, Any]:
    """
    Runs the SQL function ``compute_speed_factor`` and returns its result row as a dictionary.
    """
    from roadgraphtool.db import db

    quoted_schema = '"' + schema.replace('"', '""') + '"'
    sql = sqlalchemy.text(f"""
        SELECT *
        FROM {quoted_schema}."compute_speed_factor"(
            p_area_id => CAST(:area_id AS smallint),
            p_area_srid => CAST(:srid AS integer),
            p_demand_dataset_ids => CAST(:demand_datasets AS integer[]),
            p_start_time => CAST(:start_time AS timestamp),
            p_end_time => CAST(:end_time AS timestamp),
            p_zone_types => CAST(:zone_types AS smallint[]),
            p_ignored_zones => CAST(:ignored_zones AS bigint[]),
            p_min_duration => make_interval(secs => CAST(:min_duration_minutes AS double precision) * 60),
            p_max_duration => make_interval(secs => CAST(:max_duration_minutes AS double precision) * 60),
            p_min_ratio => CAST(:min_ratio AS double precision),
            p_max_ratio => CAST(:max_ratio AS double precision)
        )
    """)
    result = db.execute_query_to_pandas(sql, params=parameters)
    row = result.iloc[0]
    return {
        column: (float(row[column]) if column in ("speed_factor", "mean_ratio", "median_ratio") else int(row[column]))
        for column in result.columns
    }


def write_speed_calibration(result: Dict[str, Any], parameters: Dict[str, Any], output_dir: Path) -> Path:
    """
    Writes the calibration result with the parameters it was computed from to ``speed_calibration.yaml``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / RESULT_FILENAME
    with open(output_path, "w", encoding="utf-8") as outfile:
        yaml.safe_dump({"result": result, "parameters": parameters}, outfile, sort_keys=False)
    return output_path


def calibrate_speed_factor(config: SimpleNamespace, speed_calibration: SimpleNamespace, output_dir: Path) -> float:
    """
    Computes the speed factor of the configured area, logs it with the diagnostics and writes it to
    ``<output_dir>/speed_calibration.yaml``.

    :return: the speed factor, to be set as ``dm_generator.speed_factor``
    """
    parameters = build_speed_calibration_parameters(config, speed_calibration)
    result = compute_speed_factor(parameters, getattr(config, "schema", "public"))

    logging.info(
        "Speed factor of area %s: %.4f (set it as dm_generator.speed_factor)",
        parameters["area_id"],
        result["speed_factor"],
    )
    logging.info(
        "Trips: %d selected, %d used, %d without duration, %d within one zone, "
        "%d with a zone without nodes, %d filtered; %d zone pairs",
        result["trips_total"],
        result["trips_used"],
        result["trips_without_duration"],
        result["trips_intra_zone"],
        result["trips_zone_without_nodes"],
        result["trips_filtered"],
        result["zone_pairs"],
    )
    logging.info(
        "Recorded duration / network travel time of the used trips: mean %.3f, median %.3f",
        result["mean_ratio"],
        result["median_ratio"],
    )

    output_path = write_speed_calibration(result, parameters, output_dir)
    logging.info("Speed calibration written to %s", output_path)
    return result["speed_factor"]
