import geopandas as gpd
from geopandas import GeoDataFrame
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from shapely.wkt import loads

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

def load_demand_to_db(trips: DataFrame, schema: str):
    port = config.db_server_port
    connection_uri = f"postgresql://{config.username}@{config.db_host}:{port}/{config.db_name}"
    engine = create_engine(connection_uri)

    trips['geometry'] = trips['geometry'].apply(lambda geom: loads(geom) if isinstance(geom, str) else geom)

    try:
        trips.to_sql("trips", engine, if_exists="append", index=False, schema=schema)

        print("Data loaded into the database successfully.")
    except SQLAlchemyError as e:
        print("Error loading data into the database:", e)

def save_df_to_geojson(df: pd.DataFrame, filepath: str):
    df['geometry'] = df['geometry'].apply(lambda geom: loads(geom) if isinstance(geom, str) else geom)
    if not isinstance(df, gpd.GeoDataFrame):
        df = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326") # WGS84 for lon-lat

    # Save to GeoJSON
    df.to_file(filepath, driver='GeoJSON')

if __name__ == '__main__':
    # csvfile = PATH / 'porto-partials.csv'
    # csvfile = RESOURCE_PATH / 'Porto_trips.csv'
    csvfile = RESOURCE_PATH / 'Beijing_trips.csv'
    df = load_data_from_csv(csvfile)
    save_df_to_geojson(df, RESOURCE_PATH / 'Beijing_trips.geojson')
    # save_df_to_geojson(df, RESOURCE_PATH / 'Porto_trips.geojson')
    # load_demand_to_db(df, 'demand')
    # csvfile = PATH / 'Porto_trips.csv'
    # t, v = convert_CSV_format(csvfile)
    # save_format(t, v)
    # t, v = load_file()
    # load_demand_to_db(t, v, 'demand')
