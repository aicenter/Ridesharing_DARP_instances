import sys
import logging
from pathlib import Path

from roadgraphtool.config import parse_config_file, set_logging
from roadgraphtool.db import db, init_db
import roadgraphtool.pipeline


args = sys.argv
if len(args) < 2:
    logging.error("You have to provide a path to the road-graph-tool YAML config file as an argument.")
    sys.exit(1)
config_path = Path(args[1])

config = parse_config_file(config_path)
init_db(config)
set_logging(config)

# Run the RGT pipeline
roadgraphtool.pipeline.main(config)


