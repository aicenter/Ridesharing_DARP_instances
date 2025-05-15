"""
This script served as a helper to convert the demand data from the original format (CSV for Porto, TNTP for Sydney) to a format that can be used by the DARP instance generator.
"""

import ast
import csv
from pathlib import Path
from geoalchemy2 import WKTElement
import pandas as pd
import geopandas as gpd
import numpy as np
from pandas import DataFrame
from shapely.geometry import Point
from shapely.wkb import dumps as bdumps, loads as bloads
from datetime import datetime, timedelta

from darpinstances.instance_generation.demand_generation import generate_uniform_trip_times

PATH = Path(__file__).parent.parent.parent.parent
RESOURCE_PATH = PATH / "resources"

BASETIME = datetime(2014, 4, 1)

def convert_CSV_format(city: str) -> DataFrame:
    """Converts the trips from CSV format to a DataFrame with geometry."""
    input_file = RESOURCE_PATH / f"{city}_trips_og.csv"
    with open(input_file) as csvfile:
        data = list(csv.DictReader(csvfile))

    trips = []

    for request in data:
        # convert from str to list of coords
        polyline = ast.literal_eval(request["POLYLINE"])
        
        if len(polyline) < 2:
            continue

        origin = bdumps(Point(polyline[0]), hex=True)
        destination = bdumps(Point(polyline[-1]), hex=True)

        trip = {
            "timestamp": request["TIMESTAMP"],
            "origin": origin,
            "destination": destination
        }
        trips.append(trip)

    df = pd.DataFrame(trips)
    return df

def convert_TNTP_format(city: str) -> DataFrame:
    """Converts the trips from TNTP format to a DataFrame with geometry."""
    tripstntpfile = RESOURCE_PATH / f"{city}_trips_og.tntp"
    nodesfile = RESOURCE_PATH / f"{city}_node.tntp"

    # process trips to contain only valid OD flows
    flow_df = import_trips_tntp(tripstntpfile)

    # convert coordinates to proper geometry
    nodes_df = import_nodes_tntp(nodesfile)

    # add geometry coordinates to flows and generate trips
    trips_df = add_geometry_and_generate_trips(flow_df, nodes_df)
    
    # generate trips
    return trips_df

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

def add_geometry_and_generate_trips(flow_df: DataFrame, nodes_df: DataFrame, hours: int = 24) -> DataFrame:
    """Adds geometry from nodes_df to flow_df and generates trips based on OD flow.
    Default is 24 hours (one day).
    """
    data = []
    origins = nodes_df.loc[flow_df['origin'], 'geometry'].values
    destinations = nodes_df.loc[flow_df['destination'], 'geometry'].values

    print(f"Generating trips based on OD flows.")
    for i, row in flow_df.iterrows():
        flow = row['od_flow']
        
        trip_times = generate_timestamps(flow, hours)

        for ttime in trip_times:
            timestamp = (BASETIME + timedelta(milliseconds=ttime)).isoformat()
            data.append({
                'timestamp': timestamp,
                'origin': bdumps(origins[i], hex=True),
                'destination': bdumps(destinations[i], hex=True)
            })
    return pd.DataFrame(data)

def generate_timestamps(od_flow: float, N: int) -> list:
    """Generates timestamps for N hours based on OD flow.
    
    :param od_flow: OD flow (aggregated hourly traffic demand) between two nodes.
    :param n: Number of hours to generate trips for."""
    trip_counts = generate_trip_counts(od_flow, N)
    timestamps = []
    for i, trip_count in enumerate(trip_counts):
        start = i * 60 * 60
        end = (i + 1) * 60 * 60
        trip_times = generate_uniform_trip_times(start, end, trip_count)
        timestamps.extend(trip_times)
    return timestamps

def rate_func(t: int) -> float:
    """Rate function for time-varying Poisson distribution."""
    morning_peak = np.sin((np.pi / 6) * (t - 3))
    afternoon_peak = np.sin((np.pi / 12) * (t - 3))
    f = 2 + morning_peak + afternoon_peak
    return f

def generate_trip_counts(od_flow: float, N: int = 24, step: int = 1) -> list[int]:
    """Generates trip counts in N-hours interval using time-varying Poisson distribution.

    :param od_flow: OD flow (hourly traffic demand) between two nodes.
    :param N: Total hours. Default is 24 hours.
    :param step: Time step. Default is 1 hour.
    """
    rng = np.random.default_rng()
    trip_counts = [rng.poisson(od_flow * rate_func(t)) for t in np.arange(0, N, step)]
    
    return trip_counts

def load_data_from_csv(file: str) -> DataFrame:
    """Loads the data with coordinates from a CSV file."""
    df = pd.read_csv(file)
    df['origin'] = df['origin'].apply(lambda x: bloads(x, hex=True))
    df['destination'] = df['destination'].apply(lambda x: bloads(x, hex=True))

    origin = gpd.GeoSeries(df['origin'], crs="EPSG:4326").apply(lambda geom: WKTElement(geom.wkt, srid=4326))
    destination = gpd.GeoSeries(df['destination'], crs="EPSG:4326").apply(lambda geom: WKTElement(geom.wkt, srid=4326))
    df['origin'] = origin
    df['destination'] = destination
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')

    return df

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
    generate_and_save_csv("Porto")
   
    # generate_and_save_csv("Sydney")