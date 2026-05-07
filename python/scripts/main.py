import sys
import logging
from pathlib import Path

from roadgraphtool.config import parse_config_file, set_logging
import roadgraphtool.db
import roadgraphtool.pipeline


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


