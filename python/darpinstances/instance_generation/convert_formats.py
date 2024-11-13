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

# Beijing
LONGITUDE_RANGE = (115, 118)
LATITUDE_RANGE = (39, 42)

BASETIME = datetime(2014, 1, 1)
STOP_TIME_THRESHOLD = timedelta(minutes=5)
DISTANCE_THRESHOLD = 0.05
TRAJECTORY_THRESHOLD = timedelta(minutes=30)

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

def load_data_from_csv(file: str) -> DataFrame:
    """Loads the data with coordinates from a CSV file."""
    return pd.read_csv(file)

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

def generate_trips(city: str, n: int) -> DataFrame:
    flowscsvfile = RESOURCE_PATH / f"{city}_flows_no_geom.csv"
    nodesfile = RESOURCE_PATH / f"{city}_node.tntp"

    # # convert coordinates to proper geometry
    nodesfile = RESOURCE_PATH / "Sydney_node.tntp"
    nodes_df = import_nodes_tntp(nodesfile)

    # add geometry coordinates to trips
    flow_df = _sample_n_instances(load_data_from_csv(flowscsvfile), n)
    trips = add_geometry(flow_df, nodes_df)

    return trips

def _sample_n_instances(df: pd.DataFrame, n: int) -> DataFrame:
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

def calculate_distance(p1: Point, p2: Point) -> float:
    """Calculates the distance between two points.
    
    :param p1: First point in form of (lon, lat).
    :param p2: Second point in form of (lon, lat).
    :return: Distance between two points in kilometers."""
    # convert to lat, lon format
    pt1 = (p1.y, p1.x)
    pt2 = (p2.y, p2.x)
    try:
        return geodesic(pt1, pt2).km
    except ValueError as e:
        raise ValueError(f"Error calculating distance between {pt1} and {pt2}.") from e

def convert_str_to_timestamp(time: str) -> datetime:
    return datetime.fromisoformat(time)

def is_within_coords_range(lat: float, lon: float) -> bool:
    """Checks if coordinates are within specified bounds."""
    return (LATITUDE_RANGE[0] <= lat <= LATITUDE_RANGE[1] and 
            LONGITUDE_RANGE[0] <= lon <= LONGITUDE_RANGE[1])

def process_record(record: str) -> dict | None:
    """Converts record into dictionary with timestamp and Point geometry."""
    _, time, lon, lat = record.strip().split(',')
    if not is_within_coords_range(float(lat), float(lon)):
        return None
    timestamp = convert_str_to_timestamp(time)
    point = Point(float(lon), float(lat))
    return {"timestamp": timestamp, "geometry": point}

def process_trajectory(trajectory: list[str]) -> list[dict]:
    """Process a trajectory and extract trips from it 
    based on: https://arxiv.org/pdf/1602.00994."""
    trips = []
    i = 0
    while i < len(trajectory) - 1:
        start_point = process_record(trajectory[i])
        if start_point is None:  # skip invalid points
            i += 1
            continue
        current_point = start_point
        j = i + 1
        trip_formed = False
        # find destination
        while j < len(trajectory):
            next_point = process_record(trajectory[j])
            if next_point is None:  # skip invalid points
                j += 1
                continue

            distance = calculate_distance(current_point['geometry'], next_point['geometry'])
            
            if distance <= DISTANCE_THRESHOLD:
                time_diff = next_point['timestamp'] - current_point['timestamp']
                if time_diff >= STOP_TIME_THRESHOLD:
                    trips.append({
                        'origin': start_point['geometry'],
                        'destination': next_point['geometry'],
                        'timestamp': start_point['timestamp']
                    })
                    i = j
                    trip_formed = True
                    break
                current_point = next_point
            else:
                current_point = next_point
            j += 1
        if trip_formed and current_point != start_point:
            trips[-1]['destination'] = current_point['geometry']
        if not trip_formed:
            i += 1
    return trips

def convert_TXT(city: str) -> DataFrame:
    input_folder = RESOURCE_PATH / f"{city}_trips_og"
    output_folder = RESOURCE_PATH / f"{city}_trips"
    files = list(input_folder.glob("*.txt"))
    total_files = len(files)
    long_files = show_files(city)
    with tqdm(total=total_files, desc="Processing files", unit="file") as pbar:
        for f in files:
            if f.stem in long_files:
                continue
            output_file = RESOURCE_PATH / f"{f.stem}.csv"
            if output_file.exists():
                pbar.update(1)
                continue
            print("FILE: ", f)
            with open(f, 'r') as file:
                lines = file.readlines()
                if not lines: 
                    pbar.update(1)
                    continue
                trajectory = process_trajectory(lines)
            output_file = output_folder / f"{f.stem}.csv"
            pd.DataFrame(trajectory).to_csv(output_file, index=False)
            pbar.update(1)
    return pd.DataFrame(trajectory) if trajectory else pd.DataFrame()

def show_files(city: str) -> list:
    input_folder = RESOURCE_PATH / f"{city}_trips_og"
    files = list(input_folder.glob("*.txt"))
    long_files = []
    for f in files:
        with open(f, 'r') as file:
            lines = file.readlines()
            lines_count = len(lines)
            if lines_count > 20000:
                long_files.append(f.stem)
    return long_files

def count_trips(city: str) -> int:
    input_folder = RESOURCE_PATH / f"{city}_trips"
    files = list(input_folder.glob("*.csv"))
    s = 0
    for f in files:
        with open(f, 'r') as file:
            lines = file.readlines()
            lines_count = len(lines) - 1
            s += lines_count
    return s

def generate_and_save_csv(city: str):
    # save trips with geometry
    tripsfile = RESOURCE_PATH / f"{city}_trips.csv"
    match city:
        case "Sydney":
            df = convert_TNTP_format(city)
        case "Porto":
            df = convert_CSV_format(city)
        case "Beijing":
            df = convert_TXT(city)
    
    df.to_csv(tripsfile, index=False)

if __name__ == '__main__':
    # generate_and_save_csv("Porto")
    # generate_and_save_csv("Sydney")
    # convert_TXT("Beijing")
    generate_and_save_csv("Beijing")
    # print(show_files("Beijing"))
    # print(count_trips("Beijing"))

