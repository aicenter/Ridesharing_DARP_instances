from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
import geopandas as gpd
import logging
from os import path
from typing import List, Dict, Optional, Tuple

from darpinstances.db import db
from darpinstances.instance_generation.demand_generation import get_dataset_string, assign_nearest_nodes, NearestNodeProvider


def _save_vehicles_csv(vehicles: pd.DataFrame, dir: str):
    df = vehicles[['origin', 'capacity']]
    out_path = path.join(dir, 'vehicles.csv')
    logging.info("Saving vehicles to %s", out_path)
    df.to_csv(out_path, sep='\t', index=False, header=False)


def _save_vehicles_shapefile(vehicles: pd.DataFrame, nodes, crsg, dir: str):
    nodes_ = nodes.to_crs(f'epsg:{crsg}')
    pickup = vehicles[['origin']].copy()

    pickup['geometry'] = nodes_.loc[pickup['origin']].geometry.values
    pickup = gpd.GeoDataFrame(pickup, geometry='geometry', crs={'init': f'epsg:{crsg}'})

    out_filepath = path.join(dir, 'shapefiles', 'vehicles.shp')
    logging.info("Saving shapefile with vehicles to: %s", out_filepath)
    pickup.to_file(driver='ESRI Shapefile', filename=out_filepath)


def _load_datetime(string: str):
    return datetime.strptime(string, '%Y-%m-%d %H:%M:%S')


def _load_vehicle_positions_from_db(config: dict, nn_provider: NearestNodeProvider, desired_count: int, vehicle_ordering_seed:float=.123):
    count = 0
    # desired_count = config['vehicles']['vehicle_count']

    exp_time_horizon = _load_datetime(config['demand']['max_time']) - _load_datetime(config['demand']['min_time'])
    max_horizon = timedelta(hours=1)

    horizon = max_horizon
    dataset_str = get_dataset_string(config)
    srid = int(config['map']['SRID_plane'])

    while count < desired_count and horizon < 2 * max_horizon:
        veh_start = _load_datetime(config['vehicles']['start_time'])

        # sql = f"""
        # WITH vehicle_seed AS (SELECT setseed({vehicle_seed})),
        # area AS (SELECT geom FROM areas WHERE id = {config['area_id']})
        # SELECT
        #     trip_locations.origin,
        #     ST_X(nodes.geom) as x,
        #     ST_X(st_transform(nodes.geom, {srid})) as x_utm,
        #     ST_Y(nodes.geom) as y,
        #     ST_Y(st_transform(nodes.geom, {srid})) as y_utm
        # FROM demand
        # JOIN trip_locations ON dataset IN({dataset_str})
        #     AND origin_time BETWEEN '{veh_start - horizon / 2}' AND '{veh_start + horizon / 2}'
        #     AND trip_locations.request_id = demand.id
        # JOIN nodes on trip_locations.origin = nodes.id
        # JOIN area ON st_within(nodes.geom, area.geom)
        # ORDER BY random()
        # LIMIT {desired_count}
        # """

        sql = f"""
        WITH
            area AS (SELECT geom FROM areas WHERE id = {config['area_id']}),
            vd AS (
            SELECT setseed({vehicle_ordering_seed}) AS seed, null AS origin, null AS x, null AS x_utm, null AS y, null AS y_utm
            UNION ALL
            SELECT
                null AS seed,
                trip_locations.origin,
                ST_X(nodes.geom)                      as x,
                ST_X(st_transform(nodes.geom, {srid})) as x_utm,
                ST_Y(nodes.geom)                      as y,
                ST_Y(st_transform(nodes.geom, {srid})) as y_utm
            FROM demand
                  JOIN trip_locations ON dataset IN ({dataset_str})
                     AND origin_time BETWEEN '{veh_start - horizon / 2}' AND '{veh_start + horizon / 2}'
                     AND trip_locations.request_id = demand.id
                  JOIN nodes on trip_locations.origin = nodes.id
                  JOIN area ON st_within(nodes.geom, area.geom)
            offset 1
            )
        
        SELECT origin, x, x_utm, y, y_utm
        FROM vd
        ORDER BY random()
        LIMIT {desired_count};
        """

        positions = db.execute_query_to_pandas(sql)
        count = len(positions)
        if count < desired_count:
            horizon *= 1.2

    final_positions = assign_nearest_nodes(nn_provider, positions.x_utm, positions.y_utm, nn_provider.nodes)
    return final_positions


def generate_vehicles(nodes: gpd.GeoDataFrame, config: dict, nn_provider: NearestNodeProvider, desired_count: int):

    capacity = int(config["vehicles"]["vehicle_capacity"])

    columns = ['origin', 'capacity']
    vehicles = pd.DataFrame(columns=columns)

    # otherwise we use uniformly distributed init positions
    if 'positions' in config['vehicles'] and config['vehicles']['positions'] == 'random':
        vehicles['origin'] = np.random.choice(nodes.index, size=desired_count, replace=True)
    else:
        vehicles['origin'] = _load_vehicle_positions_from_db(config, nn_provider, desired_count)

    vehicles["capacity"] = capacity

    instance_dir = config['instance_dir']
    _save_vehicles_csv(vehicles, instance_dir)

    # save shapefiles
    save_shp = config["save_shp"]

    if save_shp:
        crs_geo = config['map']['SRID']
        _save_vehicles_shapefile(vehicles, nodes, crs_geo, instance_dir)
