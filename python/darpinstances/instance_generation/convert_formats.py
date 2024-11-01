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

PATH = Path(__file__).parent.parent.parent.parent

RESOURCE_PATH = PATH / "resources/"

def import_nodes_tntp(file: str) -> DataFrame:
    """Load nodes from a .tntp file convert coordinates to Point geometry."""
    nodes_df = pd.read_csv(file, delimiter='\t')
    nodes_df['geometry'] = nodes_df.apply(lambda row: Point(row['y'], row['x']), axis=1)
    nodes_df.set_index('node', inplace=True)
    nodes_df.drop(columns=['x', 'y'], inplace=True)
    return nodes_df

def import_trips_tntp(file: str) -> DataFrame:
    """Load trips from a .tntp file and keep non-null OD flows."""
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

# def generate_trips(od_flow: float, origin: Point, destination: Point, time_period: int = 100):
#     """Generate trips using a uniform distribution based on OD flows.
#     Time period is 100 hours by default."""
#     total_trips = int(od_flow * time_period)
    
#     timestamps = np.random.uniform(0, time_period, total_trips)
    
#     trips = [(origin, destination, timestamp) for timestamp in timestamps]
    
#     return trips

def add_geometry(matrix_df: DataFrame, nodes_df: DataFrame) -> DataFrame:
    """Add geometry from nodes_df to matrix_df."""
    data = []
    
    for _, row in matrix_df.iterrows():
        origin = row['origin']
        destination = row['destination']
        flow = row['od_flow']
        
        orig_coords = nodes_df.loc[origin, 'geometry']
        dest_coords = nodes_df.loc[destination, 'geometry']
        
        # trips = generate_trips(flow, orig_coords, dest_coords)

        # for trip in trips:
        #     data.append({
        #         'origin': orig_coords,
        #         'destination': dest_coords,
        #         'timestamp': trip[2],
        #     })
        data.append({
            'origin': orig_coords,
            'destination': dest_coords,
            'od_flow': flow
        })

    return pd.DataFrame(data)

def load_matrix_from_csv(file: str) -> DataFrame:
    """Load the matrix with coordinates from a CSV file."""
    return pd.read_csv(file)

def convert_TNTP_format():
    # process trips to contain only valid OD flows
    tripstntpfile = RESOURCE_PATH / "Sydney_trips.tntp"
    matrix_df = import_trips_tntp(tripstntpfile)
    flowscsvfile = RESOURCE_PATH / "Sydney_flows_no_geom.csv"
    matrix_df.to_csv(flowscsvfile, index=False)

    # convert coordinates to proper geometry
    nodesfile = RESOURCE_PATH / "Sydney_node.tntp"
    nodes_df = import_nodes_tntp(nodesfile)

    # add geometry coordinates to trips
    # matrix_df = load_matrix_from_csv(flowscsvfile)
    trips = add_geometry(matrix_df, nodes_df)

    # save trips with geometry
    tripsfile = RESOURCE_PATH / "Sydney_trips.csv"
    trips.to_csv(tripsfile, index=False)

def convert_CSV_format(filepath: str) -> tuple[GeoDataFrame, GeoDataFrame]:
    with open(filepath) as csvfile:
        data = list(csv.DictReader(csvfile))

    travel_requests = []
    vehicles = []

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

        vehicle = {
            "taxi_id": request["TAXI_ID"],
            "starting_position": Point(polyline[0])
        }
        vehicles.append(vehicle)

    travel_requests_gdf = gpd.GeoDataFrame(travel_requests, crs="EPSG:4326")
    travel_requests_gdf.set_geometry("geometry", inplace=True)

    vehicles_df = gpd.GeoDataFrame(vehicles, crs="EPSG:4326", geometry="starting_position")
    vehicles_df.set_geometry("starting_position", inplace=True)
    return travel_requests_gdf, vehicles_df

def generate_trips():
     # process trips to contain only valid OD flows
    # tripstntpfile = RESOURCE_PATH / "Sydney_trips.tntp"
    # matrix_df = import_trips_tntp(tripstntpfile)
    flowscsvfile = RESOURCE_PATH / "Sydney_flows_no_geom.csv"
    # matrix_df.to_csv(flowscsvfile, index=False)

    # # convert coordinates to proper geometry
    nodesfile = RESOURCE_PATH / "Sydney_node.tntp"
    nodes_df = import_nodes_tntp(nodesfile)

    # add geometry coordinates to trips
    # matrix_df = load_matrix_from_csv(flowscsvfile)
    matrix_df = _sample_n_instances(load_matrix_from_csv(flowscsvfile), 5000)
    trips = add_geometry(matrix_df, nodes_df)

    # save trips with geometry
    tripsfile = RESOURCE_PATH / "Sydney_trips.csv"
    trips.to_csv(tripsfile, index=False)

def _sample_n_instances(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Randomly selects N instances from the DataFrame."""
    return df.sample(n=n, replace=False).reset_index(drop=True)

def generate_trip_counts(df: DataFrame, n: int = 24) -> pd.DataFrame:
    """Generate a DataFrame with n random trip counts using Poisson distribution based on OD flow."""
    df[f'{n}h_trip_counts'] = df['od_flow'].apply(lambda x: np.sum(np.random.poisson(x, n)))
    return df

if __name__ == '__main__':
    # convert_TNTP_format()
    # generate_trips()
    tripsfile = RESOURCE_PATH / "Sydney_trips.csv"
    df = load_matrix_from_csv(tripsfile)
    trip_counts = generate_trip_counts(df)
    trip_counts.to_csv(tripsfile, index=False)
    # pass
