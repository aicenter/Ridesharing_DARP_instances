from typing import Dict, Union, Tuple
import os.path
import logging
import subprocess
import numpy as np
import geopandas as gpd
import pandas as pd

import darpinstances.instance_generation.map
import darpinstances.instance_generation.demand_generation
import darpinstances.instance_generation.vehicles
from darpinstances.instance import load_instance_config
import darpbenchmark.exec


def generate_dm(config: Dict, nodes: gpd.GeoDataFrame, edges: gpd.GeoDataFrame, allow_zero_length_edges: bool = True):
    # dm_file_path = os.path.join(config['area_dir'], "dm")
    if 'dm_filepath' in config:
        dm_file_path = config['dm_filepath']
    else:
        dm_file_path = os.path.join(config['area_dir'], 'dm.h5')

    abs_path = os.path.abspath(dm_file_path)
    abs_path_with_extension = abs_path + ".csv"
    if os.path.exists(abs_path_with_extension) or os.path.exists(abs_path):
        logging.info("Skipping DM generation, the file is already generated.")
    else:
        logging.info(f"Generating distance matrix in {abs_path_with_extension}")
        map_dir = config['map']['path']
        xeng_file_path = os.path.join(map_dir, "map.xeng")
        xeng_file_path = os.path.abspath(xeng_file_path)

        # length to travel time conversion, 50 km/h
        if 'speed' in edges:
            logging.info("Using real speed from edges")
            # estimated travel time in seconds
            edges["travel_time"] = round(edges["length"] / edges["speed"] * 3.6).astype(int)
        else:
            logging.info("Using default speed of 50 km/h")
            try:
                edges["travel_time"] = edges["length"].apply(lambda x: round(int(x) / 14))
            except ValueError as v:
                logging.warning("Suspicious max speed, trying float conversion: %s", v)
                edges["travel_time"] = edges["length"].apply(lambda x: round(float(x) / 14))

        if not allow_zero_length_edges:
            edges.loc[edges["travel_time"] == 0, 'travel_time'] = 1

        xeng = pd.DataFrame(edges[["u", "v", "travel_time"]])
        xeng["one_way"] = 1
        xeng.to_csv(xeng_file_path, sep=" ", header=["XGI", str(len(nodes)), str(len(edges)), ""], index=False)

        # call distance utils to generate dm
        command = [
            "shortestPathsPreprocessor",
            "create",
            "dm",
            "xengraph",
            "csv",
            "fast",
            xeng_file_path,
            abs_path
        ]

        darpbenchmark.exec.call_executable(command)


def generate_instance(config_filepath: str):
    config = load_instance_config(config_filepath)

    # set cwd to instance dir
    instance_dir = os.path.dirname(config_filepath)
    os.chdir(instance_dir)

    logging.info("Loading map")
    map_nodes, map_edges = darpinstances.instance_generation.map.get_map(config)

    crs_metric = config['map']['SRID_plane']
    nodes = map_nodes.to_crs(f'epsg:{crs_metric}')
    nearest_node_provider = darpinstances.instance_generation.map.NearestNodeProvider(nodes)

    # generate dm
    generate_dm(config, map_nodes, map_edges)

    # Generate trip requests
    requests = darpinstances.instance_generation.demand_generation.generate_demand(
        map_nodes, config, nearest_node_provider, crs_metric)

    # Generate vehicles
    logging.info("Generating vehicles")
    if 'vehicle_to_request_ratio' in config['vehicles']:
        desired_vehicle_count = len(requests) * config['vehicles']['vehicle_to_request_ratio']
    else:
        desired_vehicle_count = config['vehicles']['vehicle_count']
    darpinstances.instance_generation.vehicles.generate_vehicles(
        map_nodes, config, nearest_node_provider, desired_vehicle_count)
