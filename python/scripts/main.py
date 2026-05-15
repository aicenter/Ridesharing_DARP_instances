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

    # Quick rollback path to the previous Python implementation:
    # generate_positions(
    #     int(area_id),
    #     demand_datasets,
    #     demand_position_sampling.trip_location_set,
    #     start_time=getattr(demand_position_sampling, "start_time", None),
    #     end_time=getattr(demand_position_sampling, "end_time", None),
    #     zone_types=zone_types,
    #     ignored_zones=ignored_zones,
    #     print_sql=getattr(demand_position_sampling, "print_sql", False),
    # )

