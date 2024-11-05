import geopandas as gpd
from geopandas import GeoDataFrame
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from darpinstances.credentials_config import CREDENTIALS as config
from darpinstances.instance_generation.convert_formats import *

def save_format(trips: GeoDataFrame):
    """Save the trips to a SHP file."""
    trips['orig_wkt'] = trips['origin'].apply(lambda x: x.wkt)
    trips['dest_wkt'] = trips['destination'].apply(lambda x: x.wkt)
    trips.drop(columns=['origin', 'destination'], inplace=True)

    trips.to_file('resources/trips.shp', driver='ESRI Shapefile')

    print("Data saved to files.")

def load_file() -> GeoDataFrame:
    """Load the trips and vehicles GeoDataFrames from a file."""
    trips = gpd.read_file('resources/trips.shp')
    trips['origin'] = gpd.GeoSeries.from_wkt(trips['orig_wkt'])
    trips['destination'] = gpd.GeoSeries.from_wkt(trips['dest_wkt'])
    trips.drop(columns=['orig_wkt', 'dest_wkt'], inplace=True)

    return trips

def load_demand_to_db(trips: GeoDataFrame | DataFrame, schema: str):
    port = config.db_server_port
    connection_uri = f"postgresql://{config.username}@{config.db_host}:{port}/{config.db_name}"
    engine = create_engine(connection_uri)

    trips.set_geometry("geometry", inplace=True)

    try:
        trips.to_postgis("trips", engine, if_exists="append", index=False, schema=schema)

        print("Data loaded into the database successfully.")
    except SQLAlchemyError as e:
        print("Error loading data into the database:", e)

if __name__ == '__main__':
    # csvfile = PATH / 'porto-partials.csv'
    csvfile = PATH / 'Porto_trips.csv'
    # t, v = convert_CSV_format(csvfile)
    # save_format(t, v)
    # t, v = load_file()
    # load_demand_to_db(t, v, 'demand')
