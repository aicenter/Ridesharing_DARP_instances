import sys
import logging
from pathlib import Path

from roadgraphtool.config import parse_config_file, set_logging
import roadgraphtool.db
import roadgraphtool.pipeline

# from darpinstances.instance_generation.demand_positions import generate_positions


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

