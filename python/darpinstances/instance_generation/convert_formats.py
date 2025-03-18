import ast
import csv
from pathlib import Path
import time
from geoalchemy2 import WKTElement
import pandas as pd
import geopandas as gpd
import numpy as np
from pandas import DataFrame
from shapely.geometry import Point, LineString
from shapely.wkb import dumps as bdumps, loads as bloads
from shapely.wkt import loads as tloads
from datetime import datetime, timedelta
from tqdm import tqdm

from darpinstances.instance_generation.demand_generation import generate_uniform_trip_times

PATH = Path(__file__).parent.parent.parent.parent
RESOURCE_PATH = PATH / "resources"

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

        # geom = LineString(polyline)
        origin = bdumps(Point(polyline[0]), hex=True)
        destination = bdumps(Point(polyline[-1]), hex=True)

        # if not geom.is_valid:
        #     continue

        trip = {
            # "trip_id": request["TRIP_ID"],
            "timestamp": request["TIMESTAMP"],
            # "geometry": geom,
            "origin": origin,
            "destination": destination
        }
        trips.append(trip)

    df = pd.DataFrame(trips)
    return df

def convert_TNTP_format(city: str) -> DataFrame:
    # tripstntpfile = RESOURCE_PATH / f"{city}_trips_og.tntp"
    # nodesfile = RESOURCE_PATH / f"{city}_node.tntp"

    # process trips to contain only valid OD flows
    # flow_df = import_trips_tntp(tripstntpfile)
    # flowscsvfile = RESOURCE_PATH / f"{city}_flows_no_geom.csv"
    # flow_df = load_data_from_csv(flowscsvfile)

    # convert coordinates to proper geometry
    # nodes_df = import_nodes_tntp(nodesfile)

    # # add geometry coordinates to flows and generate trips
    # trips = add_geometry_and_generate_trips(flow_df, nodes_df)
    
    # add geometry    
    # trips = add_geometry(flow_df, nodes_df)

    # generate trips
    # tripsfile = RESOURCE_PATH / f"{city}_trips_geom.csv"
    # df = pd.read_csv(tripsfile)
    # trips = generate_trips(df)
    # trips = generate_trips(trips)
    chunk_trips = generate_trip_chunks(city)
    return chunk_trips

def generate_trip_chunks(city: str) -> DataFrame:
    ogtripsfile = RESOURCE_PATH / f"{city}_trips1000.csv"
    tripsfile = RESOURCE_PATH / f"{city}_trips_chunks.csv"
    df_iter = pd.read_csv(ogtripsfile, chunksize=10000)
    for df in tqdm(df_iter, desc="Generating trips"):
        chunk_trips = generate_trips(df)
        chunk_trips.to_csv(tripsfile, index=False, mode='a')
    return chunk_trips

def generate_trips(df: DataFrame, hours: int = 24) -> DataFrame:
    data = []
    for _, row in df.iterrows():
        flow = row['flow']
        trip_times = generate_timestamps(flow, hours)
        for ttime in trip_times:
            timestamp = (BASETIME + timedelta(milliseconds=ttime)).timestamp()
            orig = bloads(row['origin'], hex=True)
            dest = bloads(row['destination'], hex=True)
            data.append({
                'timestamp': timestamp,
                'origin': bdumps(Point(orig.y, orig.x), hex=True),
                'destination': bdumps(Point(dest.y, dest.x), hex=True)
            })
    return pd.DataFrame(data)

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
    """Adds geometry from nodes_df to flow_df and generates trips based on OD flow."""
    data = []
    origins = nodes_df.loc[flow_df['origin'], 'geometry'].values
    destinations = nodes_df.loc[flow_df['destination'], 'geometry'].values

    print(f"Generating trips based on OD flows.")
    tc = 0
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
            tc += 1
    print(f"Total trips generated: {tc}")
    return pd.DataFrame(data)

def add_geometry(flow_df: DataFrame, nodes_df: DataFrame) -> DataFrame:
    """Adds geometry from nodes_df to flow_df."""
    data = []
    origins = nodes_df.loc[flow_df['origin'], 'geometry'].values
    destinations = nodes_df.loc[flow_df['destination'], 'geometry'].values

    for i, row in flow_df.iterrows():
        flow = row['od_flow']
        
        data.append({
            'flow': flow,
            'origin': bdumps(origins[i], hex=True),
            'destination': bdumps(destinations[i], hex=True)
        })
    return pd.DataFrame(data)

def generate_n_trips(city: str, N: int) -> DataFrame:
    # tripstntpfile = RESOURCE_PATH / f"{city}_trips_og.tntp"
    # tripstntpfile = RESOURCE_PATH / f"Sydney_flows_no_geom.csv"
    # nodesfile = RESOURCE_PATH / f"{city}_node.tntp"
    # tripsfile = RESOURCE_PATH / f"{city}_trips_sample.csv"

    # # convert coordinates to proper geometry
    # nodes_df = import_nodes_tntp(nodesfile)

    # N randomly selected trips
    # df = load_data_from_csv(tripstntpfile)
    # df = import_trips_tntp(tripstntpfile)
    tripsfile1 = RESOURCE_PATH / f"{city}_trips3.csv"
    tripsfile = RESOURCE_PATH / f"{city}_trips.csv"
    df = pd.read_csv(tripsfile1)
    trips = df.sample(n=N, replace=False).reset_index(drop=True)

    #  # add geometry coordinates to N randomly selected trips
    # trips = add_geometry(flow_df, nodes_df)

    # save 
    trips.to_csv(tripsfile, index=False)

def generate_timestamps(od_flow: float, N: int) -> list:
    """Generates timestamps for N hours based on OD flow.
    
    :param od_flow: OD flow (hourly occurrence of vehicle) between two nodes.
    :param n: Number of hours to generate trips for."""
    trip_counts = generate_trip_counts(od_flow, N)
    timestamps = []
    if sum(trip_counts) >= 25:
        for i, trip_count in enumerate(trip_counts):
            start = i * 60 * 60
            end = (i + 1) * 60 * 60
            trip_times = generate_uniform_trip_times(start, end, trip_count)
            timestamps.extend(trip_times)
    return timestamps

def rate_func(t: int) -> float:
    """Rate function for time-varying Poisson distribution."""
    amplitude = 1.5
    morning_peak = -amplitude * np.sin((np.pi / 6) * (t + 1))
    afternoon_peak = amplitude * np.sin((np.pi / 12) * (t - 6))
    f = 1 + morning_peak + afternoon_peak
    return f

def generate_trip_counts(od_flow: float, N: int = 24, step: int = 1) -> list[int]:
    """Generates trip count in N-hours interval using time-varying Poisson distribution.

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
    # df['timestamp'] = pd.to_datetime(df['timestamp'], format='%Y-%m-%dT%H:%M:%S')

    return df

def convert_unserialized_format(city: str):
    input_file = RESOURCE_PATH / f"{city}_trips_unserialized.csv"
    output_file = RESOURCE_PATH / f"{city}_trips.csv"
    row_count = 0
    with open(input_file, mode='r') as infile, open(output_file, mode='w', newline='') as outfile:
        reader = csv.DictReader(infile)
        fieldnames = ['timestamp', 'origin', 'destination']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            orig = tloads(row['origin'])
            origin = bdumps(Point(orig.y, orig.x), hex=True)
            dest = tloads(row['destination'])
            destination = bdumps(Point(dest.y, dest.x), hex=True)
            format = '%Y-%m-%d %H:%M:%S'
            timestamp = datetime.strptime(row['timestamp'], format).timestamp()

            writer.writerow({
                'timestamp': timestamp,
                'origin': origin,
                'destination': destination
            })
            row_count += 1
    print(f"Total rows processed: {row_count}")

def generate_and_save_csv(city: str):
    # save trips with geometry
    tripsfile = RESOURCE_PATH / f"{city}_trips1000.csv"
    match city:
        case "Sydney":
            df = convert_TNTP_format(city)
        case "Porto":
            df = convert_CSV_format(city)
    
    df.to_csv(tripsfile, index=False)

if __name__ == '__main__':
    s = time.perf_counter()
    # # # generate_and_save_csv("Porto")
   
    # generate_and_save_csv("Sydney")
    n = np.random.randint(250000, 300000)
    # n = 100000
    generate_n_trips("Sydney", n)
    # # # tripstntpfile = RESOURCE_PATH / f"Sydney_trips_og.tntp"

    e = time.perf_counter()
    print(f"Geometry added in: {e-s} seconds.")