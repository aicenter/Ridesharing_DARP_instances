import geopandas as gpd
from geopandas import GeoDataFrame
from sqlalchemy.exc import SQLAlchemyError
import logging
from pandas import DataFrame
import pandas as pd

from roadgraphtool import db

def save_format(trips: GeoDataFrame):
    """Save the trips to a SHP file."""
    trips['orig_wkt'] = trips['origin'].apply(lambda x: x.wkt)
    trips['dest_wkt'] = trips['destination'].apply(lambda x: x.wkt)
    trips.drop(columns=['origin', 'destination'], inplace=True)

    trips.to_file('resources/trips.shp', driver='ESRI Shapefile')

    logging.info("Data saved to files.")

def load_file() -> GeoDataFrame:
    """Load the trips GeoDataFrames from a file."""
    trips = gpd.read_file('resources/trips.shp')
    trips['origin'] = gpd.GeoSeries.from_wkt(trips['orig_wkt'])
    trips['destination'] = gpd.GeoSeries.from_wkt(trips['dest_wkt'])
    trips.drop(columns=['orig_wkt', 'dest_wkt'], inplace=True)

    return trips

def load_demand_to_db(data: DataFrame, table: str, schema: str, dtype: dict = None):
    if hasattr(db.db.config, 'ssh'):
        db.db.set_ssh_to_db_server_and_set_port()
    db.db.set_up_db_connections()
    engine = db.db._sqlalchemy_engine

    try:
        logging.info("Loading data into the database...")
        data.to_sql(table, engine, if_exists="replace", schema=schema, chunksize=1000, index_label='id', dtype=dtype)
        logging.info("Data loaded into the database successfully.")
    except SQLAlchemyError as e:
        logging.error("Error loading data into the database:", e)

def load_table_from_db(table: str, schema: str):
    if hasattr(db.db.config, 'ssh'):
        db.db.set_ssh_to_db_server_and_set_port()
    db.db.set_up_db_connections()
    engine = db.db._sqlalchemy_engine
    
    try:
        logging.info("Loading data from the database...")
        data = pd.read_sql_table(table, engine, schema=schema)
        logging.info("Data loaded from the database successfully.")
        return data
    except SQLAlchemyError as e:
        logging.error("Error loading data from the database:", e)

def save_df_to_geojson(df: pd.DataFrame, filepath: str):
    if not isinstance(df, gpd.GeoDataFrame):
        df = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326") # WGS84 for lon-lat

    df.to_file(filepath, driver='GeoJSON')
