import geopandas as gpd
from geopandas import GeoDataFrame
from sqlalchemy.exc import SQLAlchemyError

from darpinstances.instance_generation.convert_formats import *
from roadgraphtool import db

def save_format(trips: GeoDataFrame):
    """Save the trips to a SHP file."""
    trips['orig_wkt'] = trips['origin'].apply(lambda x: x.wkt)
    trips['dest_wkt'] = trips['destination'].apply(lambda x: x.wkt)
    trips.drop(columns=['origin', 'destination'], inplace=True)

    trips.to_file('resources/trips.shp', driver='ESRI Shapefile')

    print("Data saved to files.")

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
        print("Loading data into the database...")
        data.to_sql(table, engine, if_exists="replace", schema=schema, chunksize=1000, index_label='id', dtype=dtype)
        # chunksize = 1000
        # for i in range(0, len(data), chunksize):
        #     chunk = data.iloc[i:i + chunksize]
        #     chunk.to_sql(table, engine, if_exists="replace", schema=schema, dtype=dtype)
        #     # chunk.to_sql(table, engine, if_exists="replace", schema=schema, index_label='id', dtype=dtype)
        print("Data loaded into the database successfully.")
    except SQLAlchemyError as e:
        print("Error loading data into the database:", e)

def load_table_from_db(table: str, schema: str):
    if hasattr(db.db.config, 'ssh'):
        db.db.set_ssh_to_db_server_and_set_port()
    db.db.set_up_db_connections()
    engine = db.db._sqlalchemy_engine
    
    try:
        print("Loading data from the database...")
        data = pd.read_sql_table(table, engine, schema=schema)
        print("Data loaded from the database successfully.")
        return data
    except SQLAlchemyError as e:
        print("Error loading data from the database:", e)

def save_df_to_geojson(df: pd.DataFrame, filepath: str):
    # df['geometry'] = df['geometry'].apply(lambda geom: loads(geom) if isinstance(geom, str) else geom)
    if not isinstance(df, gpd.GeoDataFrame):
        df = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326") # WGS84 for lon-lat

    df.to_file(filepath, driver='GeoJSON')

if __name__ == '__main__':
    # city = 'Porto'
    city = 'Sydney'
    # csvfile = RESOURCE_PATH / f'{city}_trips.csv'
    # df = load_data_from_csv(csvfile)
    # load_demand_to_db(df, "trips", city.lower(), {'origin': Geometry('POINT', srid=4326), 'destination': Geometry('POINT', srid=4326), 'timestamp': TIMESTAMP})
    # from darpinstances.instance_generation.demand_to_database import load_table_from_db
    # from roadgraphtool.config import parse_config_file
    # CONFIG_DB = Path('/home/dominika/Desktop/smart-mobility/road-graph-tool/config.yml')

    # config_db = parse_config_file(CONFIG_DB)
    # db.init_db(config_db)
    # porto_origin_demands_df = load_table_from_db('porto_origin_demands', 'porto')
