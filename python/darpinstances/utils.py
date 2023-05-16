import logging
from pathlib import Path

import yaml


def load_yaml(path: Path):
    with open(path, "r") as stream:
        try:
            py_yaml = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logging.error(exc)
    return py_yaml
