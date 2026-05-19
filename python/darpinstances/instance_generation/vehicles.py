from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
import geopandas as gpd
import logging
from os import path, getcwd, makedirs

import sqlalchemy

from roadgraphtool.db import db
from darpinstances.instance_generation.demand_generation import get_dataset_string, assign_nearest_nodes, NearestNodeProvider


def _save_vehicles_csv(vehicles: pd.DataFrame, dir: str):
    df = vehicles[['origin', 'capacity']]
    makedirs(dir, exist_ok=True)
    out_path = path.join(dir, 'vehicles.csv')
    logging.info("Saving vehicles to %s", out_path)
    df.to_csv(out_path, sep='\t', index=False, header=False)


def _save_vehicles_shapefile(vehicles: pd.DataFrame, nodes, crsg, dir: str):
    nodes_ = nodes.to_crs(f'epsg:{crsg}')
    pickup = vehicles[['origin']].copy()

    pickup['geometry'] = nodes_.loc[pickup['origin']].geometry.values
    pickup = gpd.GeoDataFrame(pickup, geometry='geometry', crs=f'epsg:{crsg}')

    makedirs(path.join(dir, 'shapefiles'), exist_ok=True)
    out_filepath = path.join(dir, 'shapefiles', 'vehicles.shp')
    logging.info("Saving shapefile with vehicles to: %s", out_filepath)
    pickup.to_file(driver='ESRI Shapefile', filename=out_filepath)


def _to_int_list(value):
    if value is None:
        return None
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        return [int(part.strip()) for part in value.split(",") if part.strip()]
    return [int(item) for item in value]


def _qualified_sql_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _map_db_vehicle_nodes_to_instance_nodes(vehicle_starts: pd.DataFrame, nodes: gpd.GeoDataFrame) -> pd.DataFrame:
    if 'db_id' not in nodes.columns:
        raise Exception(
            "Loaded map nodes do not contain a db_id column. "
            "Vehicle export from database sampling requires nodes.csv generated from database nodes."
        )

    node_map = nodes.reset_index()[['id', 'db_id']]
    duplicate_db_ids = node_map[node_map.duplicated('db_id', keep=False)]
    if not duplicate_db_ids.empty:
        raise Exception(
            "Loaded map nodes contain duplicate db_id values. "
            f"Examples: {duplicate_db_ids['db_id'].head(10).tolist()}"
        )

    db_id_to_instance_id = node_map.set_index('db_id')['id']
    missing_db_ids = pd.Index(vehicle_starts.origin_db_id.dropna().unique()).difference(db_id_to_instance_id.index)
    if not missing_db_ids.empty:
        raise Exception(
            "Some sampled vehicle start nodes are missing from nodes.csv/db_id mapping. "
            f"Missing count: {len(missing_db_ids)}. Examples: {missing_db_ids[:10].tolist()}"
        )

    vehicles = pd.DataFrame()
    vehicles['origin'] = vehicle_starts.origin_db_id.map(db_id_to_instance_id).astype(int)
    return vehicles


def generate_vehicles_from_db(nodes: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    logging.info("Loading vehicle start positions from DB")

    schema = config.get('schema', 'public')
    sql_function = (
        f"{_qualified_sql_identifier(schema)}."
        f"{_qualified_sql_identifier('select_vehicle_starts_for_export')}"
    )
    sql = sqlalchemy.text(f"""
        SELECT
            vehicle_index,
            origin_db_id
        FROM {sql_function}(
            CAST(:area_id AS smallint),
            CAST(:demand_dataset_ids AS integer[]),
            CAST(:trip_location_set_id AS integer),
            CAST(:trip_time_set_ids AS integer[]),
            CAST(:start_time AS timestamp),
            CAST(:end_time AS timestamp),
            CAST(:zone_types AS smallint[]),
            CAST(:vehicle_count AS integer),
            CAST(:vehicle_to_request_ratio AS real),
            CAST(:random_seed AS real)
        )
    """)
    vehicle_starts = db.execute_query_to_pandas(
        sql,
        params={
            'area_id': config['area_id'],
            'demand_dataset_ids': _to_int_list(config['demand']['dataset']),
            'trip_location_set_id': int(config['demand']['positions_set']),
            'trip_time_set_ids': _to_int_list(config['demand'].get('time_set')),
            'start_time': config['demand'].get('min_time'),
            'end_time': config['demand'].get('max_time'),
            'zone_types': _to_int_list(config.get('zone_types')),
            'vehicle_count': config['vehicles'].get('vehicle_count'),
            'vehicle_to_request_ratio': config['vehicles'].get('vehicle_to_request_ratio'),
            'random_seed': config.get('seed', 0.123),
        },
    )

    if vehicle_starts.empty:
        logging.error("No vehicle starts fetched from the database.")
        raise Exception("No vehicle starts fetched from the database.")

    vehicles = _map_db_vehicle_nodes_to_instance_nodes(vehicle_starts, nodes)
    vehicles['capacity'] = int(config['vehicles']['vehicle_capacity'])

    instance_dir = config['instance_dir']
    _save_vehicles_csv(vehicles, instance_dir)

    if config.get("save_shp", False):
        _save_vehicles_shapefile(vehicles, nodes, 4326, instance_dir)

    return vehicles


def _load_datetime(string: str):
    return datetime.strptime(string, '%Y-%m-%d %H:%M:%S')


def _load_vehicle_positions_from_db(config: dict, nn_provider: NearestNodeProvider, desired_count: int, vehicle_ordering_seed:float=.123):
    count = 0
    # desired_count = config['vehicles']['vehicle_count']

    exp_time_horizon = _load_datetime(config['demand']['max_time']) - _load_datetime(config['demand']['min_time'])

    horizon = exp_time_horizon
    dataset_str = get_dataset_string(config)
    srid = int(config['map']['SRID_plane'])

    veh_start = _load_datetime(config['vehicles']['start_time'])

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
                 AND origin_time BETWEEN '{veh_start}' AND '{veh_start + horizon}'
                 AND trip_locations.request_id = demand.id
              JOIN nodes on trip_locations.destination = nodes.id
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
        raise RuntimeError(f"Could not find enough vehicle positions. Found {count} but {desired_count} were requested.")

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
