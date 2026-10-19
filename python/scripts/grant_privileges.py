import argparse
import logging
from pathlib import Path

from sqlalchemy.dialects import postgresql

from roadgraphtool.config import parse_config_file, set_logging
from roadgraphtool.db import db, init_db
from roadgraphtool.privileges import grant_privileges as grant_rgt_privileges

# Tables written by the demand import. SELECT is needed for RETURNING and for joining back to the imported rows.
DEMAND_TABLES = [
    "dataset",
    "demand",
    "trip_location_sets",
    "trip_locations",
]

DEMAND_SEQUENCES = [
    "dataset_id_seq",
    "demand_id_seq",
    "trip_location_sets_id_seq",
]

PROCEDURES = [
    "create_demand_sampling_edges(smallint)",
]

FUNCTIONS = [
    "resolve_trip_location_set(integer, varchar)",
]


def _grant_instance_privileges(role: str, schema: str) -> None:
    quote = postgresql.dialect().identifier_preparer.quote
    role_identifier = quote(role)
    schema_identifier = quote(schema)

    def qualified(names: list[str]) -> str:
        return ", ".join(f"{schema_identifier}.{name}" for name in names)

    logging.info("Granting DARP instances privileges to role '%s'", role)
    db.execute_sql(f"GRANT SELECT, INSERT ON {qualified(DEMAND_TABLES)} TO {role_identifier}")
    db.execute_sql(f"GRANT USAGE ON SEQUENCE {qualified(DEMAND_SEQUENCES)} TO {role_identifier}")
    db.execute_sql(f"GRANT EXECUTE ON PROCEDURE {qualified(PROCEDURES)} TO {role_identifier}")
    db.execute_sql(f"GRANT EXECUTE ON FUNCTION {qualified(FUNCTIONS)} TO {role_identifier}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grant a role the privileges needed to import demand into the DARP instances database "
                    "(including the Road Graph Tool privileges)."
    )
    parser.add_argument("config", type=Path, help="path to the road-graph-tool YAML config file with the connection of a user that can grant the privileges")
    parser.add_argument("role", help="existing role that receives the privileges")
    args = parser.parse_args()

    config = parse_config_file(args.config)
    init_db(config)
    set_logging(config)

    schema = getattr(config, "schema", "public")

    # Ensure road-graph-tool privileges are granted first.
    grant_rgt_privileges(db_name=config.db.db_name, role=args.role, schema=schema)

    _grant_instance_privileges(args.role, schema)

    logging.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
