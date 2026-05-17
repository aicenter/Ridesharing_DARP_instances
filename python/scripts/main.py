import sys
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import yaml
from roadgraphtool.config import parse_config_file, set_logging
import roadgraphtool.db
import roadgraphtool.pipeline
from darpinstances.instance_generation.demand import generate_demand
from darpinstances.instance_generation.map import get_exported_map_nodes

# from darpinstances.instance_generation.demand_positions import generate_positions


def _config_to_dict(value):
    if isinstance(value, SimpleNamespace):
        return {key: _config_to_dict(item) for key, item in vars(value).items()}
    if isinstance(value, list):
        return [_config_to_dict(item) for item in value]
    return value


def _get_first_config_value(config_object, *names, default=None):
    for name in names:
        if hasattr(config_object, name):
            return getattr(config_object, name)
    return default


def _require_config_value(config_object, object_name, *names):
    value = _get_first_config_value(config_object, *names)
    if value is None:
        logging.error(
            "%s is activated but missing required field: one of %s",
            object_name,
            ", ".join(names),
        )
        sys.exit(1)
    return value


def _as_sql_id_list(value):
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _to_yaml_data(value):
    if isinstance(value, SimpleNamespace):
        return {key: _to_yaml_data(item) for key, item in vars(value).items()}
    if isinstance(value, dict):
        return {key: _to_yaml_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_yaml_data(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _is_path_like_key(key):
    if key is None:
        return False
    key = str(key).lower()
    return key.endswith("path") or key.endswith("filepath") or key.endswith("dir") or key.endswith("file")


def _relative_path_string(value, base_dir):
    path = Path(value)
    if path.is_absolute():
        return os.path.relpath(path, base_dir).replace("\\", "/")
    return str(value).replace("\\", "/")


def _relativize_config_paths(value, base_dir, key=None):
    if isinstance(value, dict):
        return {
            item_key: _relativize_config_paths(item_value, base_dir, item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_relativize_config_paths(item, base_dir, key) for item in value]
    if isinstance(value, Path):
        return _relative_path_string(value, base_dir)
    if isinstance(value, str) and _is_path_like_key(key):
        return _relative_path_string(value, base_dir)
    return value


def _validate_instance_config(instance_config):
    demand_config = instance_config.get("demand")
    if not isinstance(demand_config, dict):
        logging.error("instance_config_export output must contain a demand object.")
        sys.exit(1)
    if not demand_config.get("filepath"):
        logging.error("instance_config_export output must contain demand.filepath.")
        sys.exit(1)


def _build_demand_export_config(config, demand_export, default_instance_dir):
    export_config = _config_to_dict(config)
    export_config.update(_config_to_dict(demand_export))

    export_config["instance_dir"] = _get_first_config_value(
        demand_export,
        "instance_dir",
        default=default_instance_dir,
    )
    export_config["area_dir"] = _get_first_config_value(
        demand_export,
        "area_dir",
        default=export_config["instance_dir"],
    )
    export_config["save_shp"] = bool(
        _get_first_config_value(
            demand_export,
            "save_shp",
            default=getattr(config, "save_shp", False),
        )
    )
    export_config["finish_instance_file"] = bool(
        _get_first_config_value(
            demand_export,
            "finish_instance_file",
            default=True,
        )
    )
    export_config["area_id"] = _get_first_config_value(
        demand_export,
        "area_id",
        default=getattr(config, "area_id", None),
    )
    if export_config["area_id"] is None:
        logging.error(
            "demand_export is activated but area_id is not set: "
            "configure demand_export.area_id or top-level area_id."
        )
        sys.exit(1)

    export_map_config = _config_to_dict(getattr(config, "map", SimpleNamespace()))
    export_map_config.update(_config_to_dict(getattr(demand_export, "map", SimpleNamespace())))
    if "path" not in export_map_config:
        export_map_config["path"] = Path(export_config["area_dir"]) / "map"
    export_config["map"] = export_map_config

    demand_config = _config_to_dict(getattr(demand_export, "demand", SimpleNamespace()))
    demand_config["mode"] = _get_first_config_value(demand_export, "mode", default=demand_config.get("mode", "load"))
    demand_filepath = _get_first_config_value(
        demand_export,
        "filepath",
        "output_file",
        default=demand_config.get("filepath"),
    )
    if demand_filepath is None:
        demand_filepath = Path(export_config["instance_dir"]) / "requests.csv"
    demand_config["filepath"] = demand_filepath

    demand_config["dataset"] = _get_first_config_value(
        demand_export,
        "demand_datasets",
        "dataset_ids",
        "dataset",
        default=demand_config.get("dataset"),
    )
    if demand_config["dataset"] is None:
        logging.error("demand_export requires demand_datasets, dataset_ids, or dataset.")
        sys.exit(1)

    demand_config["positions_set"] = _get_first_config_value(
        demand_export,
        "trip_location_set",
        "positions_set",
        default=demand_config.get("positions_set"),
    )
    if demand_config["positions_set"] is None:
        logging.error("demand_export requires trip_location_set or positions_set.")
        sys.exit(1)

    trip_time_set = _get_first_config_value(
        demand_export,
        "trip_time_set",
        "time_set",
        default=demand_config.get("time_set"),
    )
    if trip_time_set is not None:
        demand_config["time_set"] = _as_sql_id_list(trip_time_set)

    demand_config["min_time"] = _get_first_config_value(
        demand_export,
        "filter_start_time",
        "start_time",
        "min_time",
        default=demand_config.get("min_time"),
    )
    demand_config["max_time"] = _get_first_config_value(
        demand_export,
        "filter_end_time",
        "end_time",
        "max_time",
        default=demand_config.get("max_time"),
    )

    export_config["demand"] = demand_config
    return export_config


def _get_demand_export_request_filepath(demand_export_config, fallback_instance_dir):
    if demand_export_config is None:
        return None

    demand_config = demand_export_config.get("demand", {})
    if demand_config.get("filepath") is not None:
        return demand_config["filepath"]

    instance_dir = demand_export_config.get("instance_dir", fallback_instance_dir)
    return Path(instance_dir) / "requests.csv"


def _build_instance_config(config, instance_config_export, default_instance_dir, demand_export_config=None):
    source = _get_first_config_value(instance_config_export, "source", "config")
    if source is not None:
        instance_config = _to_yaml_data(source)
    else:
        instance_config = {}
    if not isinstance(instance_config, dict):
        logging.error("instance_config_export.config/source must be a YAML object.")
        sys.exit(1)

    if hasattr(instance_config_export, "merge"):
        merge_config = _to_yaml_data(instance_config_export.merge)
        if not isinstance(merge_config, dict):
            logging.error("instance_config_export.merge must be a YAML object.")
            sys.exit(1)
        instance_config.update(merge_config)

    instance_dir = _get_first_config_value(
        instance_config_export,
        "instance_dir",
        default=default_instance_dir,
    )
    filepath = _get_first_config_value(
        instance_config_export,
        "filepath",
        "output_file",
        default=Path(instance_dir) / "instance.yaml",
    )

    demand_config = dict(instance_config.get("demand", {}))
    demand_export_filepath = _get_demand_export_request_filepath(
        demand_export_config,
        instance_dir,
    )
    demand_filepath_default = demand_export_filepath
    if demand_filepath_default is None:
        demand_filepath_default = demand_config.get("filepath")
    if demand_filepath_default is None:
        demand_filepath_default = Path(instance_dir) / "requests.csv"
    demand_filepath = _get_first_config_value(
        instance_config_export,
        "demand_filepath",
        "requests_file",
    )
    if demand_filepath is None:
        demand_filepath = demand_filepath_default
    if demand_filepath is not None:
        demand_config["filepath"] = str(demand_filepath)
    if demand_config:
        instance_config["demand"] = demand_config

    instance_config.pop("instance_dir", None)

    output_path = Path(filepath)
    if not output_path.is_absolute():
        output_path = Path(default_instance_dir) / output_path
    _validate_instance_config(instance_config)
    instance_config = _relativize_config_paths(
        instance_config,
        output_path.parent.resolve(),
    )

    return output_path, instance_config


args = sys.argv
if len(args) < 2:
    logging.error("You have to provide a path to the road-graph-tool YAML config file as an argument.")
    sys.exit(1)
config_path = Path(args[1])

config = parse_config_file(config_path)
set_logging(config)

roadgraphtool.db.init_db(config)
roadgraphtool.db.db._start_or_restart_ssh_connection_if_needed()

# Run the RGT pipeline
roadgraphtool.pipeline.main(config)

demand_position_sampling = getattr(config, "demand_position_sampling", None)
if demand_position_sampling is not None and getattr(
    demand_position_sampling, "activated", False
):
    area_id = getattr(demand_position_sampling, "area_id", None)
    if area_id is None:
        area_id = getattr(config, "area_id", None)
    if area_id is None:
        logging.error(
            "demand_position_sampling is activated but area_id is not set: "
            "configure demand_position_sampling.area_id or top-level area_id."
        )
        sys.exit(1)
    required = (
        "demand_datasets",
        "trip_location_set",
    )
    for key in required:
        if not hasattr(demand_position_sampling, key):
            logging.error(
                "demand_position_sampling is activated but missing required field: %s",
                key,
            )
            sys.exit(1)
    demand_datasets = demand_position_sampling.demand_datasets
    zone_types = getattr(demand_position_sampling, "zone_types", None)
    if isinstance(demand_datasets, int):
        demand_datasets = [demand_datasets]
    if isinstance(zone_types, int):
        zone_types = [zone_types]
    if zone_types is not None and len(zone_types) == 0:
        zone_types = None
    ignored_zones = getattr(demand_position_sampling, "ignored_zones", None)
    if isinstance(ignored_zones, int):
        ignored_zones = [ignored_zones]
    if ignored_zones is not None and len(ignored_zones) == 0:
        ignored_zones = None

    trip_location_set = demand_position_sampling.trip_location_set
    if isinstance(trip_location_set, int):
        trip_location_set_id = trip_location_set
        trip_location_set_description = None
    elif isinstance(trip_location_set, str):
        trip_location_set_id = None
        trip_location_set_description = trip_location_set
    else:
        logging.error(
            "demand_position_sampling.trip_location_set must be an integer id or a string description."
        )
        sys.exit(1)

    logging.info("Running demand position sampling (demand_position_sampling)")
    roadgraphtool.db.db.execute_procedure(
        "generate_demand_positions",
        named_arguments={
            "p_area_id": (int(area_id), "smallint"),
            "p_demand_dataset_ids": (demand_datasets, "integer[]"),
            "p_trip_location_set_id": (trip_location_set_id, "integer"),
            "p_trip_location_set_description": (
                trip_location_set_description,
                "varchar",
            ),
            "p_start_time": (
                getattr(demand_position_sampling, "start_time", None),
                "timestamp",
            ),
            "p_end_time": (
                getattr(demand_position_sampling, "end_time", None),
                "timestamp",
            ),
            "p_zone_types": (zone_types, "smallint[]"),
            "p_ignored_zones": (ignored_zones, "bigint[]"),
        },
        schema=getattr(config, "schema", "public"),
    )

trip_time_sampling = getattr(config, "trip_time_sampling", None)
if trip_time_sampling is not None and getattr(trip_time_sampling, "activated", False):
    required = (
        "trip_location_set",
        "trip_time_set",
        "distribution",
    )
    for key in required:
        if not hasattr(trip_time_sampling, key):
            logging.error(
                "trip_time_sampling is activated but missing required field: %s",
                key,
            )
            sys.exit(1)

    demand_datasets = getattr(
        trip_time_sampling,
        "demand_datasets",
        getattr(trip_time_sampling, "dataset_ids", None),
    )
    if isinstance(demand_datasets, int):
        demand_datasets = [demand_datasets]
    if demand_datasets is not None and len(demand_datasets) == 0:
        demand_datasets = None

    trip_time_set = trip_time_sampling.trip_time_set
    if isinstance(trip_time_set, int):
        trip_time_set_id = trip_time_set
        trip_time_set_description = None
    elif isinstance(trip_time_set, str):
        trip_time_set_id = None
        trip_time_set_description = trip_time_set
    else:
        logging.error(
            "trip_time_sampling.trip_time_set must be an integer id or a string description."
        )
        sys.exit(1)

    trip_location_set = trip_time_sampling.trip_location_set
    if not isinstance(trip_location_set, int):
        logging.error("trip_time_sampling.trip_location_set must be an integer id.")
        sys.exit(1)

    filter_start_time = getattr(trip_time_sampling, "filter_start_time", None)
    filter_end_time = getattr(trip_time_sampling, "filter_end_time", None)
    if hasattr(trip_time_sampling, "start_time"):
        if filter_start_time is not None:
            logging.error(
                "Use only one of trip_time_sampling.filter_start_time and trip_time_sampling.start_time."
            )
            sys.exit(1)
        filter_start_time = trip_time_sampling.start_time
    if hasattr(trip_time_sampling, "end_time"):
        if filter_end_time is not None:
            logging.error(
                "Use only one of trip_time_sampling.filter_end_time and trip_time_sampling.end_time."
            )
            sys.exit(1)
        filter_end_time = trip_time_sampling.end_time

    time_resolution_minutes = float(
        getattr(trip_time_sampling, "time_resolution_minutes", 60)
    )
    std_dev_minutes = getattr(trip_time_sampling, "std_dev_minutes", None)
    if std_dev_minutes is not None:
        std_dev_minutes = float(std_dev_minutes)

    logging.info("Running trip time sampling (trip_time_sampling)")
    roadgraphtool.db.db.execute_procedure(
        "generate_trip_times",
        named_arguments={
            "p_trip_location_set_id": (
                trip_location_set,
                "integer",
            ),
            "p_trip_time_set_id": (trip_time_set_id, "integer"),
            "p_trip_time_set_description": (
                trip_time_set_description,
                "varchar",
            ),
            "p_demand_dataset_ids": (demand_datasets, "integer[]"),
            "p_time_mode": (
                getattr(trip_time_sampling, "time_mode", "around_origin_time"),
                "varchar",
            ),
            "p_filter_start_time": (
                filter_start_time,
                "timestamp",
            ),
            "p_filter_end_time": (
                filter_end_time,
                "timestamp",
            ),
            "p_sample_start_time": (
                getattr(trip_time_sampling, "sample_start_time", None),
                "timestamp",
            ),
            "p_sample_end_time": (
                getattr(trip_time_sampling, "sample_end_time", None),
                "timestamp",
            ),
            "p_distribution": (trip_time_sampling.distribution, "varchar"),
            "p_time_resolution_minutes": (
                time_resolution_minutes,
                "real",
            ),
            "p_std_dev_minutes": (
                std_dev_minutes,
                "real",
            ),
        },
        schema=getattr(config, "schema", "public"),
    )

demand_export_config = None
demand_export = getattr(config, "demand_export", None)
if demand_export is not None and getattr(demand_export, "activated", False):
    demand_export_config = _build_demand_export_config(config, demand_export, config_path.parent)

    logging.info("Running demand export (demand_export)")
    map_nodes = get_exported_map_nodes(demand_export_config)

    generate_demand(
        map_nodes,
        demand_export_config,
        None,
        None,
    )

instance_config_export = getattr(config, "instance_config_export", None)
if instance_config_export is not None and getattr(
    instance_config_export,
    "activated",
    False,
):
    output_path, instance_config = _build_instance_config(
        config,
        instance_config_export,
        config_path.parent,
        demand_export_config,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info("Writing instance config to %s", output_path)
    with open(output_path, "w", encoding="utf-8") as outfile:
        yaml.safe_dump(instance_config, outfile, sort_keys=False)
