from geoalchemy2 import Geometry, WKTElement
import geopandas as gpd
from geopandas import GeoDataFrame
from sqlalchemy import TIMESTAMP, create_engine
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

def load_demand_to_db(trips: GeoDataFrame, schema: str):
    port = config.db_server_port
    connection_uri = f"postgresql://{config.username}:{config.db_password}@{config.db_host}:{port}/{config.db_name}"
    engine = create_engine(connection_uri)

    # trips['geometry'] = trips['geometry'].apply(lambda geom: loads(geom) if isinstance(geom, str) else geom)
    # trips['origin_wkt'] = trips['origin'].apply(lambda geom: WKTElement(geom.wkt, srid=4326))
    # trips['destination_wkt'] = trips['destination'].apply(lambda geom: WKTElement(geom.wkt, srid=4326))

    # trips_db = trips[['id', 'timestamp', 'origin_wkt', 'destination_wkt']]
    try:
        print("Loading data into the database...")
        # trips.to_sql("trips", engine, if_exists="replace", schema=schema, chunksize=1000, index_label='id', dtype={'origin': Geometry('POINT', srid=4326), 'destination': Geometry('POINT', srid=4326), 'timestamp': TIMESTAMP})
        chunksize = 1000
        for i in range(0, len(trips), chunksize):
            chunk = trips.iloc[i:i + chunksize]
            chunk.to_sql("trips", engine, if_exists="append", schema=schema, index_label='id', dtype={'origin': Geometry('POINT', srid=4326), 'destination': Geometry('POINT', srid=4326), 'timestamp': TIMESTAMP})
        print("Data loaded into the database successfully.")
    except SQLAlchemyError as e:
        print("Error loading data into the database:", e)

def save_df_to_geojson(df: pd.DataFrame, filepath: str):
    # df['geometry'] = df['geometry'].apply(lambda geom: loads(geom) if isinstance(geom, str) else geom)
    if not isinstance(df, gpd.GeoDataFrame):
        df = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326") # WGS84 for lon-lat

    # Save to GeoJSON
    df.to_file(filepath, driver='GeoJSON')

if __name__ == '__main__':
    # city = 'Porto'
    city = 'Sydney'
    csvfile = RESOURCE_PATH / f'{city}_trips.csv'
    gdf = load_data_from_csv(csvfile)
    # save_df_to_geojson(df, RESOURCE_PATH / f'{city}_trips.geojson')
    load_demand_to_db(gdf, city.lower())

    # csvfile = PATH / 'Porto_trips.csv'
    # t = convert_CSV_format(csvfile)
    # save_format(t)
    # t = load_file()
    # load_demand_to_db(t, 'demand')
