import ast
import csv
from pathlib import Path
import pandas as pd
import numpy as np
from pandas import DataFrame
from shapely.geometry import Point, LineString
from datetime import datetime, timedelta
from geopy.distance import geodesic
from tqdm import tqdm

from darpinstances.instance_generation.demand_generation import generate_uniform_trip_times

PATH = Path(__file__).parent.parent.parent.parent
RESOURCE_PATH = PATH / "resources/"

BASETIME = datetime(2014, 1, 1)

def convert_CSV_format(city: str) -> DataFrame:
    input_file = RESOURCE_PATH / f"{city}_trips_og.csv"
    with open(input_file) as csvfile:
        data = list(csv.DictReader(csvfile))

    trips = []

    for request in data:
        # convert from str to list of coords
        polyline = ast.literal_eval(request["POLYLINE"])
        
        if len(polyline) < 2:
            continue

        geom = LineString(polyline)
        origin = Point(polyline[0])
        destination = Point(polyline[-1])

        if not geom.is_valid:
            continue

        trip = {
            "trip_id": request["TRIP_ID"],
            "timestamp": request["TIMESTAMP"],
            "geometry": geom,
            "origin": origin,
            "destination": destination
        }
        trips.append(trip)

    df = pd.DataFrame(trips)
    return df

def convert_TNTP_format(city: str):
    tripstntpfile = RESOURCE_PATH / f"{city}_trips_og.tntp"
    nodesfile = RESOURCE_PATH / f"{city}_node.tntp"
    tripsfile = RESOURCE_PATH / f"{city}_trips.csv"

    # process trips to contain only valid OD flows
    # flowscsvfile = RESOURCE_PATH / f"{city}_flows_no_geom.csv"
    # flow_df = load_data_from_csv(flowscsvfile)
    flow_df = import_trips_tntp(tripstntpfile)

    # convert coordinates to proper geometry
    nodes_df = import_nodes_tntp(nodesfile)

    # add geometry coordinates to flows and generate trips
    trips = add_geometry(flow_df, nodes_df)

    # save trips to CSV
    trips.to_csv(tripsfile, index=False)

def import_nodes_tntp(file: str) -> DataFrame:
    """Loads nodes from a TNTP file and converts coordinates to Point geometry."""
    nodes_df = pd.read_csv(file, delimiter='\t')
    # we want point in form of lon, lat
    nodes_df['geometry'] = nodes_df.apply(lambda row: Point(row['y'], row['x']), axis=1)
    nodes_df.set_index('node', inplace=True)
    nodes_df.drop(columns=['x', 'y'], inplace=True)
    return nodes_df

def import_trips_tntp(file: str) -> DataFrame:
    """Loads trips from a TNTP file and keeps non-null OD flows."""
    with open(file, 'r') as f:
        all_rows = f.read()

    blocks = all_rows.split('Origin')[1:]
    data = []

    for block in blocks:
        lines = block.strip().split('\n')
        origin = int(lines[0])
        
        for line in lines[1:]:
            destination_data = eval('{' + line.replace(';', ',').replace(' ', '') + '}')
            for destination, value in destination_data.items():
                if value != 0:
                    data.append({'origin': origin, 'destination': int(destination), 'od_flow': value})

    matrix_df = pd.DataFrame(data)
    return matrix_df

def add_geometry(flow_df: DataFrame, nodes_df: DataFrame, hours: int = 24) -> DataFrame:
    """Adds geometry from nodes_df to flow_df and generates trips based on OD flow."""
    data = []
    
    for _, row in flow_df.iterrows():
        origin = row['origin']
        destination = row['destination']
        flow = row['od_flow']
        
        orig_coords = nodes_df.loc[origin, 'geometry']
        dest_coords = nodes_df.loc[destination, 'geometry']
        
        trip_count = generate_trip_counts(flow, hours)
        seconds = hours * 60 * 60
        trip_times = generate_uniform_trip_times(0, seconds, trip_count)

        for ttime in trip_times:
            timestamp = BASETIME + timedelta(milliseconds=ttime)
            data.append({
                'origin': orig_coords,
                'destination': dest_coords,
                'timestamp': timestamp
            })

    return pd.DataFrame(data)

def generate_n_trips(city: str, N: int) -> DataFrame:
    flowscsvfile = RESOURCE_PATH / f"{city}_flows_no_geom.csv"
    nodesfile = RESOURCE_PATH / f"{city}_node.tntp"

    # # convert coordinates to proper geometry
    nodesfile = RESOURCE_PATH / "Sydney_node.tntp"
    nodes_df = import_nodes_tntp(nodesfile)

    # add geometry coordinates to N randomly selected trips
    df = load_data_from_csv(flowscsvfile)
    flow_df = df.sample(n=N, replace=False).reset_index(drop=True)
    trips = add_geometry(flow_df, nodes_df)

    return trips

def generate_trip_counts(od_flow: float, n: int = 24) -> int:
    """Generates trip count in N-hours interval using Poisson distribution.

    :param n: Number of hours to generate trips for.
    :param od_flow: OD flow (hourly occurrence of vehicle) between two nodes.
    """
    rng = np.random.default_rng()
    trip_count = np.sum(rng.poisson(od_flow, n))
    return trip_count

def load_data_from_csv(file: str) -> DataFrame:
    """Loads the data with coordinates from a CSV file."""
    return pd.read_csv(file)

def generate_and_save_csv(city: str):
    # save trips with geometry
    tripsfile = RESOURCE_PATH / f"{city}_trips.csv"
    match city:
        case "Sydney":
            df = convert_TNTP_format(city)
        case "Porto":
            df = convert_CSV_format(city)
    
    df.to_csv(tripsfile, index=False)

if __name__ == '__main__':
    # generate_and_save_csv("Porto")
    # generate_and_save_csv("Sydney")
    pass
