import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Union

from darpinstances.inout import load_yaml


def get_instance_config_path_from_experiment_config_path(experiment_config_path: Path):
    exp_config = load_yaml(experiment_config_path)
    instance_config_path = (experiment_config_path.parent / Path(exp_config["instance"])).resolve()
    return instance_config_path


class TimeLoader:
    def __init__(self, instance_date: datetime = None):
        """
        Initialize TimeLoader with optional instance_date.
        
        Args:
            instance_date: Base datetime for relative timestamps. If None, absolute timestamps are used.
        """
        self.instance_date = instance_date
    
    def load_time_field(self, time_value: Union[int, str]) -> datetime:
        """
        Load a datetime from either a timestamp (int) or a datetime string.
        
        Args:
            time_value: Either a timestamp (int) or a datetime string (str)
            
        Returns:
            datetime: The parsed datetime object
        """
        if isinstance(time_value, str):
            # if the string contains a space, it is a datetime string
            if ' ' in time_value:
                return datetime.strptime(time_value, '%Y-%m-%d %H:%M:%S')
            # otherwise, it is a timestamp
            time_value = int(time_value)

        if self.instance_date is not None:
            return self.instance_date + timedelta(seconds=time_value)

        return datetime.fromtimestamp(time_value, tz=timezone.utc)


def load_time_field(time_value: Union[int, str], instance_date: datetime=None) -> datetime:
    """
    Convenience function for backward compatibility.
    Load a datetime from either a timestamp (int) or a datetime string.
    
    Args:
        time_value: Either a timestamp (int) or a datetime string (str)
        instance_date: Base datetime for relative timestamps. If None, absolute timestamps are used.
        
    Returns:
        datetime: The parsed datetime object
    """
    loader = TimeLoader(instance_date)
    return loader.load_time_field(time_value)



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
