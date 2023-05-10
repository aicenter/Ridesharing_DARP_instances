import configparser
from os import path, mkdir, makedirs
import geopandas as gpd
import pandas as pd
import logging


def save_trips_csv(trips, outpath: str):
    df = trips[['time_ms', 'origin', 'dest']]
    logging.info("Saving trips to %s", outpath)
    df.to_csv(outpath, sep='\t', index=False)


def prepare_config(case_name: str):
    config = configparser.ConfigParser()
    config.read('config.ini')
    case_name = case_name if case_name else 'DEFAULT'
    if case_name not in config:
        print(f'Config section for {case_name} not found.')
        exit(-1)
    params = config[case_name]
    params['outputDir'] = path.join(params['outputDir'], params['name'])
    if not path.exists(params['outputDir']):
        makedirs(params['outputDir'])
    return params
