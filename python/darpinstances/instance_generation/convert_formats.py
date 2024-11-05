import ast
import csv
from pathlib import Path
import pandas as pd
import geopandas as gpd
import numpy as np
from pandas import DataFrame
import geopandas as gpd
from geopandas import GeoDataFrame
from shapely.geometry import Point, LineString
from datetime import datetime, timedelta

from darpinstances.instance_generation.demand_generation import generate_uniform_trip_times

PATH = Path(__file__).parent.parent.parent.parent
RESOURCE_PATH = PATH / "resources/"
BASETIME = datetime(2014, 1, 1)

def import_nodes_tntp(file: str) -> DataFrame:
    """Loads nodes from a TNTP file and converts coordinates to Point geometry."""
    nodes_df = pd.read_csv(file, delimiter='\t')
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

def add_geometry(matrix_df: DataFrame, nodes_df: DataFrame, hours: int = 24) -> DataFrame:
    """Adds geometry to matrix_df and generates trips based on OD flow."""
    data = []
    
    for _, row in matrix_df.iterrows():
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

def load_matrix_from_csv(file: str) -> DataFrame:
    """Loads the matrix with coordinates from a CSV file."""
    return pd.read_csv(file)

def convert_TNTP_format(city: str):
    tripstntpfile = RESOURCE_PATH / f"{city}_trips.tntp"
    nodesfile = RESOURCE_PATH / f"{city}_node.tntp"
    tripsfile = RESOURCE_PATH / f"{city}_trips.csv"

    # process trips to contain only valid OD flows
    flowscsvfile = RESOURCE_PATH / f"{city}_flows_no_geom.csv"
    matrix_df = load_matrix_from_csv(flowscsvfile)
    # matrix_df = import_trips_tntp(tripstntpfile)

    # convert coordinates to proper geometry
    nodes_df = import_nodes_tntp(nodesfile)

    # add geometry coordinates to flows and generate trips
    trips = add_geometry(matrix_df, nodes_df)

    # save trips to CSV
    trips.to_csv(tripsfile, index=False)

def convert_CSV_format(city: str) -> GeoDataFrame:
    input_file = RESOURCE_PATH / f"{city}_trips.csv"
    with open(input_file) as csvfile:
        data = list(csv.DictReader(csvfile))

    travel_requests = []

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

        trip_req = {
            "trip_id": request["TRIP_ID"],
            "timestamp": request["TIMESTAMP"],
            "geometry": geom,
            "origin": origin,
            "destination": destination
        }
        travel_requests.append(trip_req)

    travel_requests_gdf = gpd.GeoDataFrame(travel_requests, crs="EPSG:4326")
    travel_requests_gdf.set_geometry("geometry", inplace=True)

    return travel_requests_gdf

def generate_trips(city: str):
    flowscsvfile = RESOURCE_PATH / f"{city}_flows_no_geom.csv"
    nodesfile = RESOURCE_PATH / f"{city}_node.tntp"
    tripsfile = RESOURCE_PATH / f"{city}_trips.csv"

    # # convert coordinates to proper geometry
    nodesfile = RESOURCE_PATH / "Sydney_node.tntp"
    nodes_df = import_nodes_tntp(nodesfile)

    # add geometry coordinates to trips
    matrix_df = _sample_n_instances(load_matrix_from_csv(flowscsvfile), 5000)
    trips = add_geometry(matrix_df, nodes_df)

    # save trips with geometry
    tripsfile = RESOURCE_PATH / "Sydney_trips.csv"
    trips.to_csv(tripsfile, index=False)

def _sample_n_instances(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Randomly selects N instances from the DataFrame."""
    return df.sample(n=n, replace=False).reset_index(drop=True)

def generate_trip_counts(od_flow: float, n: int = 24) -> int:
    """Generates trip count in N-hours interval using Poisson distribution.

    :param n: Number of hours to generate trips for.
    :param od_flow: OD flow (hourly occurrence of vehicle) between two nodes.
    """
    rng = np.random.default_rng()
    trip_count = np.sum(rng.poisson(od_flow, n))
    return trip_count

def convert_TXT(city: str):
    pass

if __name__ == '__main__':
    # convert_CSV_format("Porto")
    # convert_TNTP_format("Sydney")
    # generate_trips("Sydney")
    # convert_TXT("Beijing")
