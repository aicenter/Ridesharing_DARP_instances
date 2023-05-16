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


def get_instance_config_path_from_experiment_config_path(experiment_config_path: Path):
    exp_config = load_yaml(experiment_config_path)
    instance_config_path = (experiment_config_path.parent / Path(exp_config["instance"])).resolve()
    return instance_config_path
