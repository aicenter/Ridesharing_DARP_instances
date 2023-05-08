import logging
import os.path
from pathlib import Path

import numpy as np
import osmnx as ox
import networkx as nx
from os import path
from typing import Dict, Tuple, Union
import geopandas as gpd
import pandas as pd
from os import path, mkdir, makedirs
from scipy.spatial import KDTree

from DARP_instances.db import db


class NearestNodeProvider:
    def __init__(self, nodes: gpd.GeoDataFrame):
        self.nodes = nodes

        # build the kdtree
        self.KD_tree = KDTree(np.array((nodes.geometry.x, nodes.geometry.y)).T)

    def get_nearest_node(self, x, y) -> Union[Tuple[int, int], Tuple[np.array, np.array]]:
        """
        Returns the nearest node id and a distance to the nearest node. An array of coordinates can be used to compute
        the nearest nodes for multiple coordinates at once.
        :param x: x coordinate, or array of coordinates
        :param y: y coordinate, or array of coordinates
        :return: tuple[node_id, distance]
        """
        dist, index_in_kdtree = self.KD_tree.query(np.array((x, y)).T, k=1, workers=-1)
        return self.nodes.index[index_in_kdtree], dist


def add_node_highway_tags(nodes, G):
    for u, v, d in G.edges(data=True):
        if 'highway' in d.keys():
            tag = d['highway']
            tag = tag[0] if isinstance(tag, list) else tag
            nodes.loc[nodes.index[[u]], 'highway'] = tag
            nodes.loc[nodes.index[[v]], 'highway'] = tag


def _get_map_nodes_from_db(config: dict) -> gpd.GeoDataFrame:
    logging.info("Fetching nodes from db")
    sql = f"""
    DROP TABLE IF EXISTS demand_nodes;
    
    CREATE TEMP TABLE demand_nodes(
        id int,
        db_id bigint,
        x float,
        y float,
        geom geometry
    );
    
    INSERT INTO demand_nodes
    SELECT * FROM select_network_nodes_in_area({config['area_id']}::smallint);
        
    SELECT
        id,
        db_id,
        x,
        y,
        geom
    FROM demand_nodes
    """
    return db.execute_query_to_geopandas(sql)


def _get_map_edges_from_db(config: dict) -> gpd.GeoDataFrame:
    logging.info("Fetching edges from db")
    sql = f"""
        SELECT
            from_nodes.id AS u,
            to_nodes.id AS v,
            "from" AS db_id_from,
            "to" AS db_id_to,
            edges.geom as geom,
            st_length(st_transform(edges.geom, {config['map']['SRID_plane']})) as length,
            speed
        FROM edges
            JOIN demand_nodes from_nodes ON edges."from" = from_nodes.db_id
            JOIN demand_nodes to_nodes ON edges."to" = to_nodes.db_id
        WHERE
            edges.area = {config['area_id']}::smallint -- This is to support overlapping areas. For using anohther 
                                                        --area for edges (like for Manhattan), new edge_are_id param 
                                                        -- should be added to congig.yaml
    """
    edges = db.execute_query_to_geopandas(sql)

    if len(edges) == 0:
        logging.error("No edges selected")
        logging.info(sql)
        raise Exception("No edges selected")

    return edges


def _get_map_from_db(config: dict) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    nodes = _get_map_nodes_from_db(config)
    logging.info(f"{len(nodes)} nodes fetched from db")
    edges = _get_map_edges_from_db(config)
    logging.info(f"{len(edges)} edges fetched from db")
    return nodes, edges


def _get_map(config) -> tuple:
    """
    Download map using map/place property from config
    :param config: config
    :return: nodes and edges
    """

    # download map using osmnx
    place = config["map"]['place']
    logging.info("Downloading map for %s", place)
    road_network = ox.graph_from_place(place, network_type='drive', simplify=True)

    # strongly connected component
    strongly_connected_components = sorted(nx.strongly_connected_components(road_network), key=len, reverse=True)
    road_network = road_network.subgraph(strongly_connected_components[0])

    logging.info("Relabeling nodes")
    road_network = nx.relabel.convert_node_labels_to_integers(road_network, label_attribute="osmid")
    nodes, edges = ox.graph_to_gdfs(road_network)

    logging.info("Processing nodes")
    if "highway" not in nodes:
        nodes["highway"] = "empty"
    nodes = nodes[['x', 'y', 'osmid', 'geometry', 'highway']]
    nodes["id"] = nodes.index
    add_node_highway_tags(nodes, road_network)

    logging.info("Processing edges")
    edges = edges.reset_index()
    edges = edges[['u', 'v', 'length', 'highway']]

    return nodes, edges


def _save_map_csv(map_dir: os.path, nodes: gpd.GeoDataFrame, edges: pd.DataFrame):
    makedirs(map_dir, exist_ok=True)
    nodes_path = path.join(map_dir, 'nodes.csv')
    logging.info("Saving map nodes to %s", nodes_path)
    nodes_for_export = nodes.loc[:, nodes.columns != 'geom']
    nodes_for_export.to_csv(nodes_path, sep='\t', index=False)

    edges_path = path.join(map_dir, 'edges.csv')
    logging.info("Saving map edges to %s", edges_path)
    edges_for_export = edges.loc[:, edges.columns != 'geom']
    edges_for_export.to_csv(edges_path, sep='\t', index=False)


def _save_graph_shapefile(nodes: gpd.GeoDataFrame, edges: gpd.GeoDataFrame, shapefile_folder_path: str):
    filepath = Path(shapefile_folder_path)
    logging.info("Saving map shapefile to: %s", filepath.absolute())

    # if save folder does not already exist, create it (shapefiles get saved as set of files)
    filepath.mkdir(parents=True, exist_ok=True)
    filepath_nodes = filepath / "nodes.shp"
    filepath_edges = filepath / "edges.shp"

    # save the nodes and edges as separate ESRI shapefiles
    nodes.to_file(str(filepath_nodes), driver="ESRI Shapefile", index=False, encoding="utf-8")
    edges.to_file(str(filepath_edges), driver="ESRI Shapefile", index=False, encoding="utf-8")


def get_map(config: Dict) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Loads filtered map nodes geodataframe. If th dataframe is not generated yet, then the map is downloaded
    and processed to obtain the filtered nodes dataframe
    :param config: instance configuration
    :return: geodataframe containing filtered nodes that are intended for demand generation
    """
    area_dir = config['area_dir']
    map_dir = os.path.join(area_dir, 'map')

    nodes_file_path = path.join(map_dir, 'nodes.csv')

    # map already generated -> load
    if path.exists(nodes_file_path):
        logging.info("Loading nodes from %s", path.abspath(nodes_file_path))
        nodes = pd.read_csv(nodes_file_path, index_col=None, delim_whitespace=True)
        nodes = gpd.GeoDataFrame(
            nodes,
            geometry=gpd.points_from_xy(nodes.x, nodes.y),
            crs=f'epsg:{config["map"]["SRID"]}'
        )
        edges_file_path = path.join(map_dir, 'edges.csv')
        logging.info("Loading edges from %s", path.abspath(edges_file_path))
        edges = pd.read_csv(edges_file_path, index_col=None, delim_whitespace=True)

    # download and process map
    else:
        if 'place' in config['map']:
            nodes, edges = _get_map(config)
        else:
            nodes, edges = _get_map_from_db(config)

        # save map to shapefile (for visualising)
        map_dir = config["map"]["path"]
        shapefile_folder_path = path.join(map_dir, "shapefiles")
        _save_graph_shapefile(nodes, edges, shapefile_folder_path)

        # save data
        makedirs(area_dir, exist_ok=True)
        _save_map_csv(map_dir, nodes, edges)

    # Filter nodes by config/area. Only these nodes should be used for demand/vehicle generation/selection
    if 'area' in config:
        sql = f"""SELECT geom FROM areas WHERE name = '{config['area']}'"""
        area_shape = db.execute_query_to_geopandas(sql)
        mask = nodes.within(area_shape.loc[0, 'geom'])
        nodes = nodes.loc[mask]

    # set index to id column: this is needed for the shapefile export
    nodes.set_index('id', inplace=True)

    return nodes, edges
