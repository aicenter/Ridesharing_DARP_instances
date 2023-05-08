import logging
import os
from os import makedirs, path
from typing import Dict, Tuple, Union

import geopandas as gpd
import numpy as np
import numpy.random
import pandas as pd
from shapely.geometry import box
from sklearn.cluster import KMeans

import DARP_instances
from DARP_instances.db import db
from DARP_instances.instance_generation.demand_generation_helpers import save_trips_csv
from DARP_instances.instance_generation.map import NearestNodeProvider


def generate_demand(nodes: gpd.GeoDataFrame, config: Dict, nearest_node_provider: NearestNodeProvider, crs_metric: str) \
        -> pd.DataFrame:
    """
    This function creates demand and vehicles.
    :param config: instance configuration
    @param all_nodes: nodes
    """
    instance_dir = config['instance_dir']
    outpath = path.join(instance_dir, 'trips.csv')
    if path.exists(outpath):
        logging.info(f"The demand file is already in {path.abspath(outpath)}, skipping demand generation.")
        return pd.read_csv(outpath)

    logging.info("Generating demand")
    # # remove nodes located on highways, reindex
    # unused_roads = {highway_tag for highway_tag in config['map']['unused_roads']}
    # nodes = all_nodes[~all_nodes['highway'].isin(unused_roads)]

    if config['demand']['mode'] == 'generate':
        # compute cluster centroids
        n_clusters = num_clusters(nodes, crs_metric, config['demand']['cluster_size'])
        centroids = cluster_points(nodes, n_clusters)

        trips = _generate_demand_with_uniformly_distributed_positions(config, nodes, centroids, nearest_node_provider)
    elif config['demand']['mode'] == 'load':
        trips = load_demand(config, nearest_node_provider)
    else:
        raise Exception('Unsupported demand generation mode')

    # save generated trips
    save_trips_csv(trips, outpath)

    # save shapefiles
    save_shp = config["save_shp"]
    crs_geo = config['map']['SRID']

    # generate final instance file
    instance_dir = config['instance_dir']
    trips_file_path = "{}/trips.csv".format(instance_dir)

    instance_file_path = config["demand"]["filepath"]
    DARP_instances.instance_generation.demand_generation.finish_instance_file(
        trips_file_path,
        instance_file_path
    )

    if save_shp:
        save_shapefiles(trips, nodes, crs_geo, instance_dir)

    return trips


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


def load_demand(config: Dict, nearest_node_provider: NearestNodeProvider):
    use_generated_times = 'time_set' in config['demand']

    if use_generated_times:
        time_select = 'trip_times.time AS origin_time'
    else:
        time_select = 'demand.origin_time'

    srid = int(config['map']['SRID_plane'])
    dataset_str = get_dataset_string(config)

    sql = f"""
    SELECT 
        {time_select}, 
        ST_X(origin_nodes.geom) as ox, 
        ST_X(st_transform(origin_nodes.geom, {srid})) as ox_utm,
        ST_Y(origin_nodes.geom) as oy,
        ST_Y(st_transform(origin_nodes.geom, {srid})) as oy_utm,
        ST_X(destination_nodes.geom) AS dx,
        ST_X(st_transform(destination_nodes.geom, {srid})) as dx_utm,
        ST_Y(destination_nodes.geom) AS dy,
        ST_Y(st_transform(destination_nodes.geom, {srid})) as dy_utm
    FROM demand
    JOIN trip_locations
        ON trip_locations.request_id = demand.id
        AND dataset IN ({dataset_str})
        AND origin_time BETWEEN '{config['demand']['min_time']}' AND '{config['demand']['max_time']}'
        AND set = {config['demand']['positions_set']}
    JOIN nodes AS origin_nodes ON
        origin_nodes.id = trip_locations.origin
        
    JOIN nodes AS destination_nodes 
        ON destination_nodes.id = trip_locations.destination
        AND destination_nodes.id != origin_nodes.id
    """

    if use_generated_times:
        sql = f"""
            {sql}
            JOIN trip_times 
                ON trip_times.request_id = demand.id 
                AND trip_times.set IN ({config['demand']['time_set']})
                AND time BETWEEN '{config['demand']['min_time']}' AND '{config['demand']['max_time']}'
        """

    # if "area" in config:
    sql = f"""
                WITH area AS (SELECT geom FROM areas WHERE id = {config['area_id']})
                {sql}
                    JOIN area ON st_within(origin_nodes.geom, area.geom)
                        AND st_within(destination_nodes.geom, area.geom)
            """

    sql = f"""
        {sql}
        ORDER BY origin_time
    """
    # print(sql)

    logging.info("Loading demand from DB")
    demand = db.execute_query_to_pandas(sql)

    if demand.empty:
        logging.error("No requests fetched the database.")
        logging.info(f"SQL: {sql}")
        raise Exception("No requests fetched the database.")

    logging.info(f"{len(demand)} requests fetched from db")

    trips = pd.DataFrame()

    logging.info('Assigning nearest nodes')
    trips['origin'] \
        = assign_nearest_nodes(nearest_node_provider, demand.ox_utm, demand.oy_utm, nearest_node_provider.nodes)
    trips['dest'] = \
        assign_nearest_nodes(nearest_node_provider, demand.dx_utm, demand.dy_utm, nearest_node_provider.nodes)
    trips['time_ms'] \
        = ((demand.origin_time.dt.hour * 60 + demand.origin_time.dt.minute) * 60 + demand.origin_time.dt.second) * 1000

    return trips


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


def finish_instance_file(
        trips_filepath: str,
        out_filepath: str
):
    trips = pd.read_csv(trips_filepath, delim_whitespace=True)

    trips["time_ms"] = trips["time_ms"].apply(lambda x: round(x))

    os.makedirs(os.path.dirname(out_filepath), exist_ok=True)
    logging.info("Saving instance file to %s", out_filepath)
    trips.to_csv(out_filepath, sep=" ", header=False, mode="a")


def save_shapefiles(trips, nodes, crsg, dir):
    nodes_ = nodes.to_crs(f'epsg:{crsg}')
    pickup = trips[['time_ms', 'origin']].copy()

    pickup['geometry'] = nodes_.loc[pickup['origin']].geometry.values
    pickup = gpd.GeoDataFrame(pickup, geometry='geometry', crs=f'epsg:{crsg}')
    makedirs(path.join(dir, 'shapefiles'), exist_ok=True)
    pickups_filepath = path.join(dir, 'shapefiles', 'pickup.shp')
    logging.info("Saving shapefile with pickups to: %s", pickups_filepath)
    pickup.to_file(driver='ESRI Shapefile', filename=pickups_filepath)

    drop_off = trips[['time_ms', 'dest']].copy()
    drop_off['geometry'] = nodes_.loc[drop_off['dest']].geometry.values
    drop_off = gpd.GeoDataFrame(drop_off, geometry='geometry', crs=f'epsg:{crsg}')
    drop_offs_filepath = path.join(dir, 'shapefiles', 'dropoff.shp')
    logging.info("Saving shapefile with drop offs to: %s", drop_offs_filepath)
    drop_off.to_file(driver='ESRI Shapefile', filename=drop_offs_filepath)
