import logging
import math
from pathlib import Path

from darpinstances.inout import load_yaml


def get_instance_config_path_from_experiment_config_path(experiment_config_path: Path):
    exp_config = load_yaml(experiment_config_path)
    instance_config_path = (experiment_config_path.parent / Path(exp_config["instance"])).resolve()
    return instance_config_path


def load_dm_mem_size_GB(instances_path: Path):
    logging.info(f"Distance matrix sizes")
    dm_sizes = {}
    for dmf in instances_path.rglob("**/dm.h5"):
        dm_size_bytes = dmf.stat().st_size
        dm_size_GB = math.ceil(dm_size_bytes / 10 ** (3 * 3))
        logging.info(f"DM-{dmf.parent.name}: {dm_size_GB}")
        dm_sizes[dmf.parent.name] = dm_size_GB
    assert len(dm_sizes) > 0, f"seems like no distance matrices were found in {instances_path}"
    return dm_sizes
