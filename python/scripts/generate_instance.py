import os
import logging
from pathlib import Path
from shapely import wkt
from geoalchemy2 import Geometry
from sqlalchemy import TIMESTAMP, BigInteger, Integer
import pandas as pd
import geopandas as gpd

from darpbenchmark.sizing import calculate_sizing_for_instance
from darpinstances.instance_generation.demand_to_database import load_data_from_csv, load_demand_to_db
from darpinstances.instance_generation.demand_generation import generate_demand
from darpinstances.instance_generation.vehicles import generate_vehicles
from scripts.convert_formats import RESOURCE_path, generate_and_save_csv
from darpinstances.instance_generation.map import NearestNodeProvider, get_map
from darpinstances.instance_generation.instance_generation import generate_dm
from darpinstances.instance import load_instance_config
from roadgraphtool import db
from roadgraphtool.config import parse_config_file

config_db = Path('/home/dominika/Desktop/smart-mobility/road-graph-tool/config.yml')
path = Path.cwd()
main_instance_dir = path.parent / "Instances"
main_results_dir = path.parent / "Results"

def initialize_db(config_path: Path):
    config = parse_config_file(config_path)
    db.init_db(config)


def replace_positions_with_nearest_nodes(demand_filepath: str, og_demands: pd.DataFrame, nodesdata, nearest_node_provider: NearestNodeProvider):
    demand_trips = []
    for i, row in og_demands.iterrows():
        orig = wkt.loads(str(row['origin']))
        nearest_orig = nearest_node_provider.get_nearest_node(orig.x, orig.y)
        orig_db_id = nodesdata.loc[nearest_orig[0], 'db_id']
        dest = wkt.loads(str(row['destination']))
        nearest_dest = nearest_node_provider.get_nearest_node(dest.x, dest.y)
        dest_db_id = nodesdata.loc[nearest_dest[0], 'db_id']
        origin_time = row['timestamp']
        dataset = 1
        trip = {
            "origin": orig_db_id,
            "destination": dest_db_id,
            "origin_time": origin_time,
            "dataset": dataset
        }
        demand_trips.append(trip)
    demand_df = pd.DataFrame(demand_trips)
    demand_df.to_csv(demand_filepath, index=False)
    return demand_df

def map_demand_to_existing_nodes(cityname: str, nodes: gpd.GeoDataFrame, nearest_node_provider: NearestNodeProvider):
    demand_filepath = RESOURCE_path / f'{cityname}_demand.csv'
    if os.path.exists(demand_filepath):
        demand_df = pd.read_csv(demand_filepath)
    else:
        csvfile = RESOURCE_path / f'{cityname}_trips.csv'
        og_demands = load_data_from_csv(csvfile)
        demand_df = replace_positions_with_nearest_nodes(demand_filepath, og_demands, nodes, nearest_node_provider)
    return demand_df

def generate_instance(city: str, instance_config_path: Path, results_path: Path):
    config_instance = load_instance_config(instance_config_path)
    instance_dir = os.path.dirname(instance_config_path)
    os.chdir(instance_dir)

    # Load filtered map nodes and edges
    logging.info("Loading map")
    map_nodes, map_edges = get_map(config_instance)

    # Set up nearest node provider
    crs_metric = config_instance['map']['SRID']
    nodes = map_nodes.to_crs(f'epsg:{crs_metric}')
    nnp = NearestNodeProvider(nodes)

    # Map demand to existing nodes if not already done
    df = map_demand_to_existing_nodes(city, nodes, nnp)
    # load_demand_to_db(df, "tmp_demand", city.lower(), {'origin': BigInteger, 'destination': BigInteger, 'origin_time': TIMESTAMP, 'dataset': Integer})
    # insert_query = f"""INSERT INTO public.demand (id, origin, destination, origin_time, dataset)
    # select id, origin, destination, origin_time, dataset from {city.lower()}.tmp_demand;"""
    # db.db.execute_sql(insert_query, schema='public')

    # Generate DM
    generate_dm(config_instance, map_nodes, map_edges, False)

    # Generate trip requests
    crs_metric = config_instance['map']['SRID_plane']
    requests_df = generate_demand(map_nodes, config_instance, nnp, crs_metric)

    # Generate vehicles
    if 'vehicle_count' in config_instance['vehicles']:
        vehicle_count = int(config_instance['vehicles']['vehicle_count'])
    else:
        vehicle_count = len(requests_df) # vehicle_to_request_ratio = 1 in this case
    generate_vehicles(map_nodes, config_instance, nnp, vehicle_count)

    # Calculate sizing
    # calculate_sizing_for_instance(results_path)
    logging.info("INSTANCE GENERATED.\n")

def create_custom_results_config(instance_path, method, outdir):
    config = {}
    config['instance'] = instance_path
    config['method'] = method
    config['outdir'] = outdir
    return config

if __name__ == "__main__":
    initialize_db(config_db)
    # city = "Porto"
    city = "Sydney"
    start_durations = {'07-00': ['16_h'], '18-00': ['2_h', '30_min', '15_min', '05_min']}
    delays = ['03_min', '05_min', '10_min']
    method = 'ih'
    for start, durations in start_durations.items():
        for duration in durations:
            for delay in delays:
                instance_config_path = main_instance_dir / f'{city}/instances/' / f'start_{start}' / f'duration_{duration}' / f'max_delay_{delay}' / 'config.yaml'
                results_path = main_results_dir / f'{city}' / f'start_{start}' / f'duration_{duration}' / f'max_delay_{delay}' / method / 'config.yaml'
                results_sol = results_path.parent / "config.yaml-solution.json"
                if not results_sol.exists():
                    generate_instance(city, instance_config_path, results_path)
                else:
                    logging.info(f"Generated instance already exists: {start}, {duration}, {delay}")

    # from datetime import datetime, timedelta
    # from darpinstances.instance_generation.generate_config import generate_config, default_config
    # start_durations_str = {'07-00': ['16_h'], '18-00': ['2_h', '01_min', '30_min', '15_min', '05_min']}
    # start_durations = {7: [16*60], 18: [180, 1, 30, 15, 5]}
    # delays_str = ['03_min', '05_min', '10_min']
    # delays = [3, 5, 10]
    # method = 'ih'

    # for start, durations in start_durations.items():
    #     for i, duration in enumerate(durations):
    #         for j, delay in enumerate(delays):
    #             if start == 7:
    #                 min_time = datetime(2014, 1, 1, 7, 0, 0)
    #                 start_str = '07-00'
    #             else:
    #                 min_time = datetime(2014, 1, 1, 18, 0, 0)
    #                 start_str = '18-00'
    #             max_time = min_time + timedelta(minutes=duration)
    #             start_time = min_time - timedelta(minutes=30)
                
    #             instance_dir = main_instance_dir / f'{city}/instances/' / f'start_{start_str}' / f'duration_{start_durations_str[start_str][i]}' / f'max_delay_{delays_str[j]}'
    #             results_dir = main_results_dir / f'{city}' / f'start_{start_str}' / f'duration_{start_durations_str[start_str][i]}' / f'max_delay_{delays_str[j]}' / method
                
    #             # os.makedirs(instance_dir, exist_ok=True)
    #             os.makedirs(results_dir, exist_ok=True)
                
    #             instance_path = instance_dir / "config.yaml"
    #             results_path = results_dir / "config.yaml"

    #             # instance_config = create_custom_instance_config(3, delay*60, 32756, min_time.strftime('%Y-%m-%d %H:%M:%S'), max_time.strftime('%Y-%m-%d %H:%M:%S'), start_time.strftime('%Y-%m-%d %H:%M:%S'), 2, 2, 2)
