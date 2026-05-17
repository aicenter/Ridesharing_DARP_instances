import logging
import os
from os import makedirs, path
from typing import Dict, Tuple, Union

import geopandas as gpd
import numpy as np
import numpy.random
import pandas as pd
import sqlalchemy
from shapely.geometry import box
from sklearn.cluster import KMeans

import darpinstances
from roadgraphtool.db import db
from darpinstances.instance_generation.demand_generation_helpers import save_requests_csv
from darpinstances.instance_generation.map import NearestNodeProvider


def generate_demand(nodes: gpd.GeoDataFrame, demand_export_config: Dict, nearest_node_provider: NearestNodeProvider, crs_metric: str) \
        -> pd.DataFrame:
    """
    This function creates demand and vehicles.
    :param config: instance configuration
    @param all_nodes: nodes
    """
    instance_dir = demand_export_config['instance_dir']
    outpath = path.join(instance_dir, 'requests.csv')
    if path.exists(outpath):
        logging.info(f"The demand file is already in {path.abspath(outpath)}, skipping demand export.")
        return pd.read_csv(outpath)

    if demand_export_config['demand']['mode'] == 'generate':
        logging.info("Generating demand")
        # compute cluster centroids
        n_clusters = num_clusters(nodes, crs_metric, demand_export_config['demand']['cluster_size'])
        centroids = cluster_points(nodes, n_clusters)

        requests = _generate_demand_with_uniformly_distributed_positions(demand_export_config, nodes, centroids, nearest_node_provider)
    elif demand_export_config['demand']['mode'] == 'load':
        requests = load_demand(demand_export_config, nodes)
    else:
        raise Exception('Unsupported demand generation mode')

    # save generated requests
    save_requests_csv(requests, outpath)

    # save shapefiles
    if demand_export_config.get("save_shp", True):
        save_shapefiles(requests, nodes, instance_dir)

    return requests


def _generate_demand_with_uniformly_distributed_positions(
        config: Dict,
        nodes: gpd.GeoDataFrame,
        centroids: pd.DataFrame,
        nearest_node_provider: NearestNodeProvider
):
    """
    Generates demand
    :param nearest_node_provider: provides nearest node id
    :param config: configuration
    :param nodes: projected map nodes
    :param centroids: centroids of the demand clusters
    :return:
    """
    num_requests = config['demand']['request_count']
    peak_hours = config['demand']['peaks']
    avg_dist = config['demand']['avg_distance']
    min_dist = config['demand']['min_distance']

    # add some more trips to be able to remove too short trips later
    num_requests_ = int(1.1 * num_requests)
    num_peaks = len(peak_hours)
    num_trips_p = 0 if num_peaks == 0 else int(num_requests_ * 0.4)
    trip_count_outside_peaks = num_requests_ - num_trips_p
    columns = ['time_ms', 'cluster1', 'cluster2', 'dist', 'dx', 'dy', 'origin', 'dest']
    all_trips = pd.DataFrame(columns=columns)

    # generate non-peak demand
    # generate request time and trip distance
    all_trips['time_ms'] = generate_uniform_trip_times(
        config['demand']['min_time'],
        config['demand']['max_time'],
        trip_count_outside_peaks
    )
    all_trips['dist'] = np.random.normal(avg_dist, avg_dist / 2, size=trip_count_outside_peaks)
    mask = all_trips.dist < min_dist
    all_trips.loc[mask, 'dist'] = np.random.uniform(min_dist, avg_dist, size=sum(mask))
    # origin and destination clusters, direction vector
    all_trips['cluster1'] = select_clusters(centroids.label.values, trip_count_outside_peaks,
                                            np.exp(centroids.node_count / 100))
    all_trips['cluster2'] = select_clusters(centroids.label.values, trip_count_outside_peaks,
                                            np.exp(centroids.node_count / 100))
    all_trips = cluster_to_vector(all_trips, centroids)
    # select nodes
    all_trips = select_nodes(all_trips, nodes, nearest_node_provider)

    # peak demand
    if num_peaks != 0:
        peak_n = num_trips_p // num_peaks
        probs = [centroids.from_center, 1 / centroids.from_center]

        for peak in peak_hours:
            start = peak['start']
            end = peak['end']
            # higher probabilities for:
            # morning pickup/evening dropoff - further from center
            # evening pickup/morning dropoff - closer to center
            probs_p = probs[0] if start <= 12 else probs[1]
            probs_d = probs[1] if start > 12 else probs[0]

            new_trips = pd.DataFrame(columns=columns)
            # times, distances
            new_trips['time_ms'] = generate_normal_trip_times(start, end, peak_n, 95)
            new_trips['dist'] = np.random.normal(avg_dist, avg_dist / 2, size=peak_n)
            mask = (new_trips.dist < min_dist)
            new_trips.loc[mask, 'dist'] = np.random.uniform(min_dist, avg_dist, size=sum(mask))
            # clusters, directions, nodes
            new_trips['cluster1'] = select_clusters(centroids.label.values, peak_n, probs_p)
            new_trips['cluster2'] = select_clusters(centroids.label.values, peak_n, probs_d)
            new_trips = cluster_to_vector(new_trips, centroids)
            new_trips = select_nodes(new_trips, nodes, nearest_node_provider)
            # add to main dataframe
            all_trips = pd.concat([all_trips, new_trips], axis=0)

    # filter out too short trips
    all_trips['dist'] = all_trips.apply(
        lambda t: nodes.loc[t.origin].geometry.distance(nodes.loc[t.dest].geometry),
        axis=1)
    all_trips = all_trips[all_trips.dist >= min_dist]
    all_trips = all_trips[(all_trips['time_ms'] >= 0) & (all_trips['time_ms'] < 24 * 36e5)]
    all_trips = all_trips.reset_index(drop=True)

    # if more than required trips were generated, remove random rows
    num_generated = all_trips.shape[0]
    num_to_remove = num_generated - num_requests
    if num_to_remove > 0:
        to_remove = np.random.choice(all_trips.index, size=num_to_remove, replace=False)
        all_trips = all_trips.drop(to_remove)
    # sort by pickup time and reindex
    all_trips = all_trips.sort_values(by='time_ms').reset_index(drop=True)

    # translate back to original indices
    # all_trips['origin'] = nodes.iloc[all_trips.origin].id.values
    # all_trips['dest'] = nodes.iloc[all_trips.dest].id.values

    return all_trips


def assign_nearest_nodes(nearest_node_provider: NearestNodeProvider, xcol: pd.Series, ycol: pd.Series,
                         nodes: gpd.GeoDataFrame):
    # the script fails if the nearest node is more than this far from the position loaded from the database
    max_distance = 1000
    indices, distances = nearest_node_provider.get_nearest_node(xcol, ycol)
    if max(distances) > max_distance:
        max_index = distances.argmax()
        orig_coord_str = f"[{xcol[max_index]}, {ycol[max_index]}]"
        nearest_node = nodes.loc[indices[max_index]]
        nearest_coord_str = f"[{nearest_node.geometry.x}, {nearest_node.geometry.y}]"
        raise Exception(f"""A node is too far from the coordinates loaded from db. Distance: {max(distances)} m.
        Coordinates loaded from db: {orig_coord_str}
        Nearest point: {nearest_coord_str}
        """)
    return indices


def get_dataset_string(config: dict) -> str:
    dataset = config['demand']['dataset']
    dataset_str = str(dataset) if isinstance(dataset, int) \
        else ", ".join((str(dataset_id) for dataset_id in config['demand']['dataset']))
    return dataset_str


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


def _map_db_nodes_to_instance_nodes(demand: pd.DataFrame, nodes: gpd.GeoDataFrame) -> pd.DataFrame:
    if 'db_id' not in nodes.columns:
        raise Exception(
            "Loaded map nodes do not contain a db_id column. "
            "Demand export from trip_locations requires nodes.csv generated from database nodes."
        )

    node_map = nodes.reset_index()[['id', 'db_id']]
    duplicate_db_ids = node_map[node_map.duplicated('db_id', keep=False)]
    if not duplicate_db_ids.empty:
        raise Exception(
            "Loaded map nodes contain duplicate db_id values. "
            f"Examples: {duplicate_db_ids['db_id'].head(10).tolist()}"
        )

    db_id_to_instance_id = node_map.set_index('db_id')['id']
    required_db_ids = pd.Index(
        pd.concat([demand.origin_db_id, demand.destination_db_id], ignore_index=True)
        .dropna()
        .unique()
    )
    missing_db_ids = required_db_ids.difference(db_id_to_instance_id.index)
    if not missing_db_ids.empty:
        raise Exception(
            "Some sampled demand nodes are missing from nodes.csv/db_id mapping. "
            f"Missing count: {len(missing_db_ids)}. Examples: {missing_db_ids[:10].tolist()}"
        )

    trips = pd.DataFrame()
    trips['origin'] = demand.origin_db_id.map(db_id_to_instance_id).astype(int)
    trips['dest'] = demand.destination_db_id.map(db_id_to_instance_id).astype(int)
    trips['time_ms'] = (
        (
            demand.request_time.dt.hour * 60
            + demand.request_time.dt.minute
        ) * 60
        + demand.request_time.dt.second
    ) * 1000
    return trips


def load_demand(config: Dict, nodes: gpd.GeoDataFrame):
    logging.info("Loading demand from DB")
    schema = config.get('schema', 'public')
    sql_function = (
        f"{_qualified_sql_identifier(schema)}."
        f"{_qualified_sql_identifier('select_demand_for_export')}"
    )
    sql = sqlalchemy.text(f"""
        SELECT
            request_id,
            request_time,
            origin_db_id,
            destination_db_id
        FROM {sql_function}(
            CAST(:area_id AS smallint),
            CAST(:demand_dataset_ids AS integer[]),
            CAST(:trip_location_set_id AS integer),
            CAST(:trip_time_set_ids AS integer[]),
            CAST(:start_time AS timestamp),
            CAST(:end_time AS timestamp)
        )
    """)
    demand = db.execute_query_to_pandas(
        sql,
        params={
            'area_id': config['area_id'],
            'demand_dataset_ids': _to_int_list(config['demand']['dataset']),
            'trip_location_set_id': int(config['demand']['positions_set']),
            'trip_time_set_ids': _to_int_list(config['demand'].get('time_set')),
            'start_time': config['demand'].get('min_time'),
            'end_time': config['demand'].get('max_time'),
        },
    )

    if demand.empty:
        logging.error("No requests fetched the database.")
        raise Exception("No requests fetched the database.")

    logging.info(f"{len(demand)} requests fetched from db")
    demand['request_time'] = pd.to_datetime(demand['request_time'])
    return _map_db_nodes_to_instance_nodes(demand, nodes)


def cluster_to_vector(trips, centroids):
    trips['dx'] = centroids.iloc[trips.cluster2].x.values - centroids.iloc[trips.cluster1].x.values
    trips['dy'] = centroids.iloc[trips.cluster2].y.values - centroids.iloc[trips.cluster1].y.values
    # origin and destination in the same cluster
    mask = (trips.dx == 0) & (trips.dy == 0)
    trips.loc[mask, 'dx'] = np.random.uniform(-1, 1, size=sum(mask))
    trips.loc[mask, 'dy'] = np.random.uniform(-1, 1, size=sum(mask))
    trips['norm'] = np.sqrt(trips.dx ** 2 + trips.dy ** 2)
    trips['dx'] = trips['dx'] / trips['norm']
    trips['dy'] = trips['dy'] / trips['norm']
    trips = trips.drop(columns=['norm'])
    return trips


def select_nodes(trips, nodes, nearest_node_provider: NearestNodeProvider):
    """
    Select nodes from nodes dataframe for cluster labels in trips.
    :param tree:
    :param trips:
    :param nodes:
    :return:
    """

    p_clusters = trips.cluster1.unique()
    for c in p_clusters:
        cluster_nodes = nodes[nodes.centroid_label == c].index
        mask = trips.cluster1 == c
        trips.loc[mask, 'origin'] = np.random.choice(cluster_nodes, size=sum(mask), replace=True)

    trips['x2'] = nodes.loc[trips['origin']].geometry.x.values + trips.dx * trips.dist
    trips['y2'] = nodes.loc[trips['origin']].geometry.y.values + trips.dy * trips.dist

    idx = nearest_node_provider.get_nearest_node(trips.x2, trips.y2)
    trips['dest'] = idx
    trips = trips.drop(columns=['x2', 'y2'])
    return trips


def select_vehicle_nodes(vehicles: pd.DataFrame, nodes):
    """
    Select nodes from nodes dataframe for cluster labels in vehicles.
    :param trips:
    :param nodes:
    :return:
    """

    p_clusters = vehicles.cluster1.unique()
    for c in p_clusters:
        cluster_nodes = nodes[nodes.centroid_label == c].index
        mask = vehicles.cluster1 == c
        vehicles.loc[mask, 'origin'] = np.random.choice(cluster_nodes, size=sum(mask), replace=True)

    return vehicles


def select_clusters(points, num_points, probs=None):
    probs = probs if probs is not None else np.ones(len(points))
    if np.sum(probs) != 1:
        probs = probs / np.sum(probs)
    result = np.random.choice(points, size=num_points, p=probs)
    return result


def cluster_points(points: gpd.GeoDataFrame, num_clusters: int) -> pd.DataFrame:
    """
    Cluster points, add 'label column with centroid label to points dataframe.
    Returns dataframe with clusters' centroids (label, x, y, node_count, from_center)
    where node count is the number of nodes in the cluster,
    and 'from_center' is distance of between the cluster centroid and the city center in meters.

    :param points: geodataframe with 'geometry' column
    :param num_clusters: number of required clusters
    :return: geodataframe with cluster centroids
    """
    coords = np.array([points.geometry.x, points.geometry.y]).T
    kmeans = KMeans(n_clusters=num_clusters, random_state=0).fit(coords)
    centroids = kmeans.cluster_centers_

    points['centroid_label'] = kmeans.labels_
    df = pd.DataFrame(np.array([range(len(centroids)), centroids.T[0], centroids.T[1]]).T,
                      columns=['label', 'x', 'y'])
    df['label'] = df.label.apply(int)

    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.x, df.y), crs=points.crs)
    city_center = box(*points.unary_union.bounds).centroid
    gdf['from_center'] = gdf.geometry.apply(lambda point: point.distance(city_center))
    gdf['node_count'] = gdf.label.apply(lambda label: len([l for l in kmeans.labels_ if l == label]))

    return gdf


def generate_normal_trip_times(min_time: int, max_time: int, n: int, ci: int = 99):
    """
    Returns n request times [ms] with normal distribution st  ci% of requests falls between the start and end limit.
    :param min_time: earliest start time in seconds
    :param max_time: latest start time in seconds
    :param n: sample size
    :param ci: confidence interval
    :return: np.array(n, 1)
    """
    h = 24 * 36e5
    min_time *= 1000
    max_time *= 1000
    mean = (min_time + max_time) / 2
    std = compute_std(min_time, max_time, ci)

    generator = numpy.random.default_rng()
    times = generator.normal(mean, std, n)

    # rounding TODO remove and lower the resolution to seconds
    times = np.round(times / 1e3) * 1e3

    # fixing times outside the confidence interval TODO increase the confidence and use a more sofisticated method
    #  for outliers
    times[times < min_time] = mean
    times[times > max_time] = mean
    return times


def compute_std(min_time: int, max_time: int, ci) -> float:
    """
    Computes standard deviation for the given values of
     mean, sample size, and confidence interval.

    :param min_time:
    :param max_time:
    :param mean: sample mean
    :param ci: confidence interval
    :return: standard deviation
    """
    time_window_size = max_time - min_time
    zscore = {90: 1.645, 95: 1.96, 99: 2.576}
    std = time_window_size / zscore[ci]
    return std


def generate_uniform_trip_times(min_time: int, max_time: int, n: int):
    """
    Returns n request times [ms] with normal distribution st  ci% of requests falls between the start and end limit.
    :param min_time: earliest start time in seconds
    :param max_time: latest start time in seconds
    :param n: sample size
    :return: np.array(n, 1) of start times
    """
    generator = numpy.random.default_rng()
    times = generator.integers(min_time * 1000, max_time * 1000, n, endpoint=True)

    # rounding TODO remove and lower the resolution to seconds
    times = np.round(times / 1e3) * 1e3

    return times


def num_clusters(nodes_proj: gpd.GeoDataFrame, crsm: int, cluster_size: float) -> int:
    """
    Computes the number of clusters for demand generation
    :param nodes_proj: nodes with metric geometry
    :param crsm: plane SRID used to project the nodes
    :param cluster_size: target cluster area in km3
    :return: number of clusters for demand generation
    """
    # nodes_proj = nodes.to_crs(f'epsg:{crsm}')
    area_km = nodes_proj.unary_union.convex_hull.area / 1e6
    cluster_count = int(area_km / cluster_size)
    return max(cluster_count, 5)


def save_shapefiles(trips, nodes, dir):
    crs_geo = 4326
    nodes_ = nodes.to_crs(epsg=crs_geo)
    pickup = trips[['time_ms', 'origin']].copy()

    pickup['geometry'] = nodes_.loc[pickup['origin']].geometry.values
    pickup = gpd.GeoDataFrame(pickup, geometry='geometry', crs=f'epsg:{crs_geo}')
    makedirs(path.join(dir, 'shapefiles'), exist_ok=True)
    pickups_filepath = path.join(dir, 'shapefiles', 'pickup.shp')
    logging.info("Saving shapefile with pickups to: %s", pickups_filepath)
    pickup.to_file(driver='ESRI Shapefile', filename=pickups_filepath)

    drop_off = trips[['time_ms', 'dest']].copy()
    drop_off['geometry'] = nodes_.loc[drop_off['dest']].geometry.values
    drop_off = gpd.GeoDataFrame(drop_off, geometry='geometry', crs=f'epsg:{crs_geo}')
    drop_offs_filepath = path.join(dir, 'shapefiles', 'dropoff.shp')
    logging.info("Saving shapefile with drop offs to: %s", drop_offs_filepath)
    drop_off.to_file(driver='ESRI Shapefile', filename=drop_offs_filepath)
