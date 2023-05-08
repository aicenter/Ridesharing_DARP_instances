import yaml
import logging

import DARP_instances.log


default_config = {
    "map": {
        "SRID": 4326
    },
    'demand': {
    },
    'vehicles': {
        'vehicle_capacity': 4
    },
    'save_shp': True
}


def generate_config(config: dict, path: str):
    logging.info('Saving config to %s', path)
    with open(path, 'w') as outfile:
        yaml.safe_dump(config, outfile)