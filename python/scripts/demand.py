"""
Converted from `python/nb/demand.ipynb` (same cell order and source).

Cell boundaries use `# %%` (VS Code / Jupyter interactive). IPython one-line
magics from the notebook are expressed via `_ipython.run_line_magic(...)` so
the file is valid for `python demand.py` when not in IPython.
"""

try:
    from IPython import get_ipython
    _ipython = get_ipython()
except (ImportError, TypeError):
    _ipython = None

# %% --- code cell 0 ---
if _ipython is not None:
    _ipython.run_line_magic("load_ext", "autoreload")

# %% --- code cell 1 ---
if _ipython is not None:
    _ipython.run_line_magic("autoreload", "")

# %% --- code cell 2 ---
import pandas as pd
import os
import matplotlib.pyplot as plt
import pyarrow.parquet as pq
import geopandas as gpd
from sqlalchemy import create_engine
from roadgraphtool.db import db
import sys
from shapely.geometry.polygon import Polygon
from shapely.geometry.multipolygon import MultiPolygon
import plotly.express as px
from sqlalchemy.dialects.postgresql import insert
import sqlalchemy.types
import geoalchemy2
import geoalchemy2.shape
from pathlib import Path

# %% [markdown] --- cell 3 ---
# # NYC

# %% [markdown] --- cell 4 ---
# ## Monthly statistics

# %% --- code cell 5 ---
stats_path = r"D:\AIC data\demand\Manhattan/data_reports_monthly.csv"
columns = ['Month/Year', 'License Class', 'Trips Per Day',
       'Farebox Per Day', 'Unique Drivers',
       'Unique Vehicles', 'Vehicles Per Day',
       'Avg Days Vehicles on Road',
       'Avg Hours Per Day Per Vehicle',
       'Avg Days Drivers on Road',
       'Avg Hours Per Day Per Driver',
       'Avg Minutes Per Trip',
       'Percent of Trips Paid with Credit Card', 'Trips Per Day Shared']
dfsm = pd.read_csv(stats_path, header=0, names=columns, skipinitialspace=True)
dfsm['Trips Per Day'] = dfsm['Trips Per Day'].str.replace(',', '').astype('int')
dfsm

# %% --- code cell 6 ---
dfsmagg = dfsm.groupby('Month/Year').sum()
dfsmagg.sort_values('Trips Per Day', inplace=True, ascending=False)
dfsmagg

# %% --- code cell 7 ---
dfsmagg_from_2019 = dfsmagg[dfsmagg.index > '2019-01']
dfsmagg_from_2019

# %% --- code cell 8 ---
dfsmagg_from_2019_bd = dfsmagg_from_2019.sort_index()

plt.figure(figsize=(28, 5))
plt.xticks(rotation = 90)
plt.plot(dfsmagg_from_2019_bd.index, dfsmagg_from_2019_bd['Trips Per Day'])

# %% [markdown] --- cell 9 ---
# ## Common

# %% --- code cell 10 ---
def nyc_import_month(root_path: Path, year: int, month: int):
    name = f"_tripdata_{year}-{month:02d}.parquet"
    data = [
        {'filename': f"yellow{name}", 'dataset': 2, 'origin_col_name': 'PULocationID', 'destination_col_name': 'DOLocationID', 'origin_time_col_name': 'tpep_pickup_datetime', 'destination_time_col_name': 'tpep_dropoff_datetime'},
        {'filename': f"green{name}", 'dataset': 3, 'origin_col_name': 'PULocationID', 'destination_col_name': 'DOLocationID','origin_time_col_name': 'lpep_pickup_datetime', 'destination_time_col_name': 'lpep_dropoff_datetime'},
        {'filename': f"fhv{name}", 'dataset': 4, 'origin_col_name': 'PUlocationID', 'destination_col_name': 'DOlocationID','origin_time_col_name': 'pickup_datetime', 'destination_time_col_name': 'dropOff_datetime'},
        {'filename': f"fhvhv{name}", 'dataset': 5, 'origin_col_name': 'PULocationID', 'destination_col_name': 'DOLocationID','origin_time_col_name': 'pickup_datetime', 'destination_time_col_name': 'dropoff_datetime'}
    ]
    out = []

    for data_source in data:
        print(f"Importing {data_source['filename']}")
        trips = pq.read_table(root_path / Path(data_source['filename'])).to_pandas()
        trips_for_import = pd.DataFrame(trips[[
            data_source['origin_col_name'],
            data_source['destination_col_name'],
            data_source['origin_time_col_name'],
            data_source['destination_time_col_name']
        ]])
        trips_for_import.rename(
            columns={
                data_source['origin_col_name']: "origin",
                data_source['destination_col_name']: "destination",
                data_source['origin_time_col_name']: 'origin_time',
                data_source['destination_time_col_name']: 'destination_time'
            },
            inplace=True
        )
        trips_for_import['dataset'] = data_source['dataset']
        trips_for_import.dropna(inplace=True)
        out.append(trips_for_import)

    return out

# %% [markdown] --- cell 11 ---
# ## 2022-04

# %% --- code cell 12 ---
trips = nyc_import_month(Path(r"O:\Backups/AIC backup data\Demand/NYC/2022-04"), 2022, 4)
trips

# %% --- code cell 13 ---
for t in trips:
    print(f'importing {len(t)} trips')
    db.dataframe_to_db_table(t, 'demand')

# %% --- code cell 14 ---
filename = r'O:\Backups/AIC backup data\Demand/NYC/2022-04/fhvhv_tripdata_2022-04.parquet'
pq.read_table(filename).to_pandas()

# %% [markdown] --- cell 15 ---
# ### Hourly Stats

# %% --- code cell 16 ---
sql = r"SELECT extract(hour from origin_time) AS hour, count(id) FROM demand WHERE dataset IN(2, 3, 4, 5) and date(origin_time) = '2022-04-05' GROUP BY extract(hour from origin_time)"
nyc_hourly_stats = db.execute_query_to_pandas(sql)
px.line(nyc_hourly_stats, x='hour', y='count')

# %% [markdown] --- cell 17 ---
# ## Data 2022-03

# %% --- code cell 18 ---
# trips_y = pq.read_table(r"O:\Backups\AIC data\Demand/NYC/yellow_tripdata_2013-01.parquet")
# trips_y = pq.read_table(r"D:\AIC backup data\Demand/NYC/yellow_tripdata_2022-03.parquet")
# trips_y = pq.read_table(r"D:\AIC backup data\Demand/NYC/green_tripdata_2022-03.parquet")
# trips_y = pq.read_table(r"D:\AIC backup data\Demand/NYC/fhv_tripdata_2022-03.parquet")
trips_y = pq.read_table(r"D:\AIC backup data\Demand/NYC/fhvhv_tripdata_2022-03.parquet")
trips_y = trips_y.to_pandas()
trips_y

# %% --- code cell 19 ---
# trips_y_for_import = trips_y.drop(['VendorID', 'trip_distance', 'RatecodeID', 'store_and_fwd_flag', 'PULocationID', 'payment_type', 'fare_amount', 'extra', 'mta_tax'])
# trips_y_for_import = trips_y[['PULocationID', 'DOLocationID', 'lpep_pickup_datetime', 'lpep_dropoff_datetime', 'passenger_count']]
# trips_y_for_import = trips_y[['PUlocationID', 'DOlocationID', 'pickup_datetime', 'dropOff_datetime']]
trips_y_for_import = trips_y[['PULocationID', 'DOLocationID', 'pickup_datetime', 'dropoff_datetime']]
# trips_y_for_import.rename(columns={"PULocationID": "origin", "DOLocationID": "destination", "pickup_datetime": 'origin_time', "dropOff_datetime": 'destination_time'}, inplace=True)
# trips_y_for_import.rename(columns={"PUlocationID": "origin", "DOlocationID": "destination", "pickup_datetime": 'origin_time', "dropOff_datetime": 'destination_time'}, inplace=True)
trips_y_for_import.rename(columns={"PULocationID": "origin", "DOLocationID": "destination", "pickup_datetime": 'origin_time', "dropoff_datetime": 'destination_time'}, inplace=True)
trips_y_for_import['dataset'] = 5
trips_y_for_import.dropna(inplace=True)
trips_y_for_import

# %% --- code cell 20 ---
# trips_y_for_import.to_sql('demand', con, if_exists='append', index=False)
db.dataframe_to_db_table(trips_y_for_import, 'demand')

# %% --- code cell 21 ---


# %% [markdown] --- cell 22 ---
# ### Update table

# %% --- code cell 23 ---
trips_y_for_import = trips_y[['PULocationID', 'DOLocationID', 'tpep_pickup_datetime', 'tpep_dropoff_datetime']]
trips_y_for_import.rename(columns={"PULocationID": "origin", "DOLocationID": "destination", "tpep_pickup_datetime": 'origin_time', "tpep_dropoff_datetime": 'destination_time'}, inplace=True)
trips_y_for_import

# %% --- code cell 24 ---
db.dataframe_to_db_table(trips_y_for_import, 'tmp_demand')

# %% --- code cell 25 ---
sql = """
    UPDATE demand
    SET destination_time = tmp_demand.destination_time
    FROM tmp_demand
    WHERE demand.origin_time = tmp_demand.origin_time
        AND demand.origin = tmp_demand.origin,
"""

# %% --- code cell 26 ---


# %% [markdown] --- cell 27 ---
# ## Daily statistic

# %% --- code cell 28 ---
sql = r"SELECT date(origin_time), count(id) FROM demand WHERE dataset = 2 and origin_time between '2022-03-01' AND '2022-03-31' GROUP BY date(origin_time)"

# %% --- code cell 29 ---
nyc_daily_stats = db.execute_query_to_pandas(sql)
nyc_daily_stats

# %% --- code cell 30 ---
nyc_daily_stats

# %% --- code cell 31 ---
plt.figure(figsize=(25,8))
plt.plot(nyc_daily_stats['date'], nyc_daily_stats['count'])

# %% --- code cell 32 ---
nyc_daily_stats.sort_values('count')

# %% [markdown] --- cell 33 ---
# ## Hourly statistic

# %% --- code cell 34 ---
sql = r"SELECT extract(hour from origin_time) AS hour, count(id) FROM demand WHERE dataset = 2 and date(origin_time) = '2022-03-11' GROUP BY extract(hour from origin_time)"
nyc_hourly_stats = db.execute_query_to_pandas(sql)
nyc_hourly_stats

# %% --- code cell 35 ---
plt.figure(figsize=(25,8))
plt.plot(nyc_hourly_stats['hour'], nyc_hourly_stats['count'])

# %% --- code cell 36 ---
nyc_hourly_stats.sort_values('count')

# %% --- code cell 37 ---


# %% [markdown] --- cell 38 ---
# ## Zones

# %% --- code cell 39 ---
gdf = gpd.read_file(r'D:\AIC backup data\demand\NYC\zones/geo_export_06f7643a-59de-4990-93ae-1c5671a587ba.shp')
gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
gdf

# %% --- code cell 40 ---
gdf_for_insert = gdf.rename(columns={"zone": "name", "geometry": "geom", 'objectid': 'id'})
gdf_for_insert.drop(['location_i', 'shape_area', 'shape_leng', 'borough'], axis=1, inplace=True)
gdf_for_insert['dataset'] = 2
gdf_for_insert['id'] = gdf_for_insert['id'].astype(int)
gdf_for_insert.set_geometry('geom', inplace=True)
gdf_for_insert["geom"] = [MultiPolygon([feature]) if isinstance(feature, Polygon) else feature for feature in gdf_for_insert["geom"]]
gdf_for_insert

# %% --- code cell 41 ---
gdf_for_insert.to_postgis('zones', con, if_exists='append')

# %% --- code cell 42 ---
gdf_for_insert.geom[0]

# %% [markdown] --- cell 43 ---
# ## Fleet Size

# %% --- code cell 44 ---
sql = r"SELECT COUNT(id) FROM demand WHERE dataset = 2 and origin_time BETWEEN '2022-03-11 18:00' AND '2022-03-11 18:15'"
req_count = db.execute_query_to_pandas(sql)
req_count

# %% --- code cell 45 ---
sql = r"SELECT AVG(extract(EPOCH FROM (demand.destination_time - demand.origin_time))) AS avg_duration FROM demand WHERE dataset = 2 and origin_time BETWEEN '2022-03-11 18:00' AND '2022-03-11 18:15'"
avg_time_per_trip = db.execute_query_to_pandas(sql)
avg_time_per_trip = avg_time_per_trip.iloc[0]['avg_duration']
avg_time_per_trip

# %% --- code cell 46 ---
ridesharing_rate = 2 # avg vehicle occupancy. Estimated.
experiment_length = 15 # length/time horizon of the ridesharing instance

car_count = req_count / ridesharing_rate / max(experiment_length / (avg_time_per_trip / 60), 1)
car_count

# %% --- code cell 47 ---
experiment_length / (avg_time_per_trip / 60)

# %% [markdown] --- cell 48 ---
#

# %% [markdown] --- cell 49 ---
# ## Old vs new demand files

# %% --- code cell 50 ---
demand_path = Path(r"O:\Backups/AIC backup data\Demand\NYC")
trips_2013_01 = pd.read_parquet(demand_path / "yellow_tripdata_2013-01.parquet")
trips_2013_01

# %% --- code cell 51 ---
trips_2015_01 = pd.read_parquet(demand_path / "yellow_tripdata_2015-01.parquet")
trips_2015_01

# %% --- code cell 52 ---
trips_csv_2015_01 = pd.read_csv(demand_path / "yellow_tripdata_2015-01.csv")
trips_csv_2015_01

# %% --- code cell 53 ---
trips_csv_2015_01['pickup_latitude'].unique()

# %% --- code cell 54 ---
trips_csv_2016_03 = pd.read_csv(demand_path / "yellow_tripdata_2016-03.csv")
trips_csv_2016_03

# %% --- code cell 55 ---
trips_csv_2016_03['pickup_latitude'].unique()

# %% --- code cell 56 ---
trips_csv_2016_11 = pd.read_csv(demand_path / "yellow_tripdata_2016-11.csv")
trips_csv_2016_11

# %% --- code cell 57 ---
trips_csv_2016_07 = pd.read_csv(demand_path / "yellow_tripdata_2016-07.csv")
trips_csv_2016_07

# %% [markdown] --- cell 58 ---
# # Chicago

# %% [markdown] --- cell 59 ---
# ## Zones

# %% [markdown] --- cell 60 ---
# ## Comunity areas

# %% --- code cell 61 ---
gdf = gpd.read_file(r'D:\AIC backup data\demand\Chicago\zones/Comunity areas/')
gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
gdf

# %% --- code cell 62 ---
gdf_for_insert = gdf[['geometry', 'area_num_1', 'community']]
gdf_for_insert.rename(columns={"geometry": "geom", 'area_num_1': 'id', 'community': 'name'}, inplace=True)
gdf_for_insert['dataset'] = 3
gdf_for_insert['level'] = 0
gdf_for_insert.set_geometry('geom', inplace=True)
gdf_for_insert["geom"] = [MultiPolygon([feature]) if isinstance(feature, Polygon) else feature for feature in gdf_for_insert["geom"]]
gdf_for_insert

# %% --- code cell 63 ---
gdf_for_insert.to_postgis('zones', con, if_exists='append')

# %% --- code cell 64 ---


# %% [markdown] --- cell 65 ---
# ## Census Tracts

# %% --- code cell 66 ---
gdf = gpd.read_file(r'D:\AIC backup data\demand\Chicago\zones/Census tracts/')
gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
gdf

# %% --- code cell 67 ---
gdf_for_insert = gdf[['geometry', 'census_t_1']]
gdf_for_insert.rename(columns={"geometry": "geom", 'census_t_1': 'id'}, inplace=True)
gdf_for_insert['dataset'] = 3
gdf_for_insert['level'] = 1
gdf_for_insert.set_geometry('geom', inplace=True)
gdf_for_insert["geom"] = [MultiPolygon([feature]) if isinstance(feature, Polygon) else feature for feature in gdf_for_insert["geom"]]
gdf_for_insert

# %% --- code cell 68 ---
gdf_for_insert.to_postgis('zones', con, if_exists='append')

# %% [markdown] --- cell 69 ---
# ## Censtus Tracks Illinois

# %% --- code cell 70 ---
gdf = gpd.read_file(r'D:\AIC backup data\demand\Illinois')
gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
gdf

# %% --- code cell 71 ---
gdf_for_insert = gdf[['geometry', 'GEOID']]
gdf_for_insert.rename(columns={"geometry": "geom", 'GEOID': 'id'}, inplace=True)
gdf_for_insert['type'] = 1
gdf_for_insert.set_geometry('geom', inplace=True)
gdf_for_insert["geom"] = [MultiPolygon([feature]) if isinstance(feature, Polygon) else feature for feature in gdf_for_insert["geom"]]
gdf_for_insert

# %% --- code cell 72 ---
meta = sqlalchemy.MetaData()
zone_table = geoalchemy2.Table('zones', meta, autoload_with=db._sqlalchemy_engine)
insert_statement = sqlalchemy.dialects.postgresql.insert(zone_table).on_conflict_do_nothing()

# %% --- code cell 73 ---
list_to_insert = [{'id': id, 'geom': geoalchemy2.shape.from_shape(geo, srid=4326), 'type': type} for id, geo, type in zip(gdf_for_insert.id, gdf_for_insert.geom, gdf_for_insert['type'])]
list_to_insert[0]

# %% --- code cell 74 ---
db._sqlalchemy_engine.execute(insert_statement, list_to_insert)

# %% --- code cell 75 ---
insert_statement

# %% --- code cell 76 ---
# gdf_for_insert.to_postgis('zones', db._sqlalchemy_engine, if_exists='append')
gdf_for_insert.to_sql('zones', db._sqlalchemy_engine, if_exists='append', method=insert_on_duplicate, dtype={'geom': geoalchemy2.Geometry('Multipolygon', srid=4326)})

# %% --- code cell 77 ---


# %% [markdown] --- cell 78 ---
# ## Monthly statistics

# %% --- code cell 79 ---
sql = """
SELECT COUNT(1), DATE_TRUNC('month', origin_time) as month
FROM demand
WHERE dataset = 1
GROUP BY DATE_TRUNC('month', origin_time)
"""

# %% --- code cell 80 ---
monthly_stats = db.execute_query_to_pandas(sql)

# %% --- code cell 81 ---
monthly_stats.sort_values('month', inplace=True)
monthly_stats

# %% --- code cell 82 ---
px.line(monthly_stats, 'month', 'count')

# %% --- code cell 83 ---
monthly_stats['count']

# %% [markdown] --- cell 84 ---
# ## Daily statistics

# %% --- code cell 85 ---
sql = """
SELECT COUNT(1), DATE_TRUNC('day', origin_time) as day
FROM demand
WHERE dataset = 1 AND origin_time BETWEEN '2022-05-01' AND '2022-05-31 23:59:59'
GROUP BY DATE_TRUNC('day', origin_time)
"""

# %% --- code cell 86 ---
chicago_daily_stats = db.execute_query_to_pandas(sql)

# %% --- code cell 87 ---
chicago_daily_stats.sort_values('day', inplace=True)
chicago_daily_stats

# %% --- code cell 88 ---
px.line(chicago_daily_stats, 'day', 'count')

# %% [markdown] --- cell 89 ---
# ## Hourly Stats

# %% --- code cell 90 ---
sql = """
SELECT COUNT(1), DATE_TRUNC('hour', origin_time) as hour
FROM demand
WHERE dataset = 1 AND origin_time BETWEEN '2022-05-20 00:00:00' AND '2022-05-20 23:59:59'
GROUP BY DATE_TRUNC('hour', origin_time)
"""

# %% --- code cell 91 ---
chicago_hourly_stats = db.execute_query_to_pandas(sql)

# %% --- code cell 92 ---
chicago_hourly_stats.sort_values('hour', inplace=True)
chicago_hourly_stats

# %% --- code cell 93 ---
px.line(chicago_hourly_stats, 'hour', 'count')

# %% [markdown] --- cell 94 ---
# ## Trip location generation

# %% --- code cell 95 ---
demand_datasets = [1]
start_time = '2022-05-20 18:00'
end_time = '2022-05-20 18:15'
zone_types = [1, 2]
trip_location_set = 3

# %% --- code cell 96 ---
demand_set_str = ', '.join((str(did) for did in demand_datasets))
zone_type_str = ', '.join((str(zt) for zt in zone_types))
sql_base = f"""
FROM demand
	WHERE dataset IN({demand_set_str})
		AND origin_time BETWEEN '{start_time}' AND '{end_time}'
"""

# %% --- code cell 97 ---
count_sql = f"""
SELECT COUNT(1)
	{sql_base}
"""
count = db.execute_count_query(count_sql)
count

# %% --- code cell 98 ---
from_sql = f"""
FROM selected_demand
    JOIN zones AS oz ON selected_demand.origin = oz.id AND oz.type IN ({zone_type_str})
    JOIN zones AS dz ON selected_demand.destination = dz.id AND dz.type IN ({zone_type_str})
"""
count_joint_zones_sql = f"""
WITH selected_demand AS (
    SELECT *
	{sql_base}
)

SELECT COUNT(1)
    {from_sql}
"""
count_joint = db.execute_count_query(count_joint_zones_sql)
count_joint

# %% --- code cell 99 ---
count_joint_nodes_sql = f"""
WITH selected_demand AS (
    SELECT *
	{sql_base}
)

SELECT COUNT(1)
    {from_sql}
    JOIN LATERAL (
    	SELECT id
		FROM nodes
		WHERE st_contains(oz.geom, nodes.geom)
		LIMIT 1
	) as origin_nodes ON TRUE
	JOIN LATERAL (
		SELECT id
		FROM nodes
		WHERE st_contains(dz.geom, nodes.geom)
		LIMIT 1
	) as destination_nodes ON TRUE
"""
count_joint_nodes = db.execute_count_query(count_joint_nodes_sql)
count_joint_nodes

# %% --- code cell 100 ---
insert_sql = f"""
INSERT INTO trip_locations(request_id, origin, destination, set)

WITH selected_demand AS (
    SELECT *
	{sql_base}
)

SELECT
    selected_demand.id,
    origin_nodes.id as origin,
    destination_nodes.id as destination,
    {trip_location_set}
    {from_sql}
    JOIN LATERAL (
    	SELECT id
		FROM nodes
		WHERE st_contains(oz.geom, nodes.geom)
		ORDER BY random()
		LIMIT 1
	) as origin_nodes ON TRUE
	JOIN LATERAL (
		SELECT id
		FROM nodes
		WHERE st_contains(dz.geom, nodes.geom)
		ORDER BY random()
		LIMIT 1
	) as destination_nodes ON TRUE
"""

# %% --- code cell 101 ---
db.execute_sql(insert_sql)

# %% --- code cell 102 ---
debug_nodes_sql = f"""
WITH selected_demand AS (
    SELECT *
	{sql_base}
)

SELECT *
    {from_sql}
    LEFT JOIN LATERAL (
    	SELECT id
		FROM nodes
		WHERE st_contains(oz.geom, nodes.geom)
		LIMIT 1
	) as origin_nodes ON TRUE
	LEFT JOIN LATERAL (
		SELECT id
		FROM nodes
		WHERE st_contains(dz.geom, nodes.geom)
		LIMIT 1
	) as destination_nodes ON TRUE
WHERE origin_nodes.id IS NULL OR destination_nodes.id IS NULL
"""
debug_nodes = db.execute_query_to_pandas(debug_nodes_sql)
debug_nodes

# %% --- code cell 103 ---
debug_nodes[debug_nodes['id'] is None]

# %% --- code cell 104 ---
debug_nodes.columns

# %% --- code cell 105 ---


# %% [markdown] --- cell 106 ---
# # Washington DC

# %% [markdown] --- cell 107 ---
# ## Zone load

# %% --- code cell 108 ---
zones = db.execute_query_to_geopandas("SELECT * FROM zones WHERE type = 4")

# %% [markdown] --- cell 109 ---
# ## Common

# %% --- code cell 110 ---
columns=['OBJECTID', 'TRIPTYPE', 'PROVIDERNAME', 'FAREAMOUNT', 'GRATUITYAMOUNT', 'SURCHARGEAMOUNT', 'EXTRAFAREAMOUNT', 'TOLLAMOUNT', 'TOTALAMOUNT', 'PAYMENTTYPE', 'ORIGINCITY', 'ORIGINSTATE', 'ORIGINZIP', 'DESTINATIONCITY', 'DESTINATIONSTATE', 'DESTINATIONZIP', 'MILEAGE', 'DURATION', 'ORIGIN_BLOCK_LATITUDE', 'ORIGIN_BLOCK_LONGITUDE', 'ORIGIN_BLOCKNAME', 'DESTINATION_BLOCK_LAT', 'DESTINATION_BLOCK_LONG', 'DESTINATION_BLOCKNAME', 'AIRPORT', 'ORIGINDATETIME_TR', 'DESTINATIONDATETIME_TR', 'source_id'
]

def dc_load_year(year: int, root_path: Path):
    dc_df = pd.DataFrame(columns=columns)
    for file in os.listdir(root_path):
        if file.startswith(f"taxi_{str(year)}"):
            path = root_path / file
            print(f"loading data from: {path}")
            df_per_month = pd.read_csv(path)
            date = file.split('.')[0].split('_')[1]
            df_per_month['source_id'] = [int(f'{date}{id}') for id in df_per_month['OBJECTID']]
            dc_df = pd.concat([dc_df, df_per_month])

    # Filter incomplete records
    dc_df_fnan = pd.DataFrame(dc_df.query('ORIGIN_BLOCK_LATITUDE.notna() and DESTINATION_BLOCK_LAT.notna()'))
    dc_df_fnan['ORIGINDATETIME_TR'] = pd.to_datetime(dc_df_fnan['ORIGINDATETIME_TR'])
    dc_df_fnan['month'] = dc_df_fnan['ORIGINDATETIME_TR'].dt.month

    return dc_df_fnan

def join_zones(df: pd.DataFrame):
    dc_gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df['ORIGIN_BLOCK_LONGITUDE'], df['ORIGIN_BLOCK_LATITUDE']),
        crs=4326
    )
    joined = dc_gdf.sjoin(zones, how='left')
    pre_dest_join = gpd.GeoDataFrame(
        joined[['source_id', 'id', 'ORIGINDATETIME_TR', 'DESTINATIONDATETIME_TR']],
        geometry=gpd.points_from_xy(joined['DESTINATION_BLOCK_LONG'], joined['DESTINATION_BLOCK_LAT']),
        crs=4326
    )
    pre_dest_join.rename(columns={'id': 'origin'}, inplace=True)
    sec_joined = pre_dest_join.sjoin(zones, how='left')

    # check for failed joins
    failed_join = sec_joined[sec_joined['origin'].isna() | sec_joined['id'].isna()]
    if len(failed_join) > 0:
        print(f"ERROR: Failed to join {len(failed_join)} records")
        return failed_join

    return sec_joined

def import_to_db(df: gdf.GeoDataFrame):
    demand_import = pd.DataFrame(df[['source_id', 'origin', 'id', 'ORIGINDATETIME_TR', 'DESTINATIONDATETIME_TR']])
    demand_import.rename(columns={'ORIGINDATETIME_TR': 'origin_time', 'DESTINATIONDATETIME_TR': 'destination_time', 'id': 'destination'}, inplace=True)
    demand_import['dataset'] = 7
    db.dataframe_to_db_table(demand_import, 'demand')

# %% [markdown] --- cell 111 ---
# ## 2021

# %% --- code cell 112 ---
# dir_path = r"D:\AIC backup data\demand\Washington DC"
dir_path = r="O:\Backups\AIC backup data\Demand\DC\OpenDataDC_Taxi_2021"
dc_df = dc_load_year(2021, Path(dir_path))
dc_df

# %% [markdown] --- cell 113 ---
# ### Monthly statistics

# %% --- code cell 114 ---
dc_mstats = dc_df.groupby('month').size()
px.line(dc_mstats)

# %% [markdown] --- cell 115 ---
# ### Daily statistics

# %% --- code cell 116 ---
df_october = pd.DataFrame(dc_df[dc_df['month'] == 10])
df_october['day'] = df_october['ORIGINDATETIME_TR'].dt.day
dc_dstats = df_october.groupby('day').size()
px.line(dc_dstats)

# %% [markdown] --- cell 117 ---
# ### Hourly Stats

# %% --- code cell 118 ---
df_october_22 = pd.DataFrame(df_october[df_october['day'] == 22])
df_october_22['hour'] = df_october_22['ORIGINDATETIME_TR'].dt.hour
dc_hstats = df_october_22.groupby('hour').size()
px.line(dc_hstats)

# %% [markdown] --- cell 119 ---
# ## 2022

# %% --- code cell 120 ---
dir_path = r="O:\Backups\AIC backup data\Demand\DC\OpenDataDC_Taxi_2022"
# dir_path = r'D:\AIC backup data\demand\Washington DC\2022'
dc_df_2022 = dc_load_year(2022, Path(dir_path))
dc_df_2022

# %% [markdown] --- cell 121 ---
# ### Monthly statistics

# %% --- code cell 122 ---
dc_mstats = dc_df_2022.groupby('month').size()
px.line(dc_mstats)

# %% [markdown] --- cell 123 ---
# ### Daily statistics

# %% --- code cell 124 ---
df_april = pd.DataFrame(dc_df_2022[dc_df_2022['month'] == 4])
df_april['day'] = df_april['ORIGINDATETIME_TR'].dt.day
dc_dstats = df_april.groupby('day').size()
px.line(dc_dstats)

# %% [markdown] --- cell 125 ---
# ### Import

# %% --- code cell 126 ---
joined = join_zones(df_april)
joined

# %% --- code cell 127 ---
import_to_db(df_april)

# %% [markdown] --- cell 128 ---
# ### Hourly Stats

# %% --- code cell 129 ---
df_april_5 = pd.DataFrame(df_april[df_april['day'] == 5])
df_april_5['hour'] = df_april_5['ORIGINDATETIME_TR'].dt.hour
dc_hstats = df_april_5.groupby('hour').size()
px.line(dc_hstats)

# %% [markdown] --- cell 130 ---
# ## 24 h demand import

# %% --- code cell 131 ---


# %% --- code cell 132 ---
db.dataframe_to_db_table(demand_import, 'demand')

# %% --- code cell 133 ---
demand_db = db.execute_query_to_pandas("SELECT * FROM trip_times WHERE set = 2")
demand_db

# %% --- code cell 134 ---
px.histogram(demand_db['time'])

# %% --- code cell 135 ---


# %% [markdown] --- cell 136 ---
# ## 1 hour demand

# %% --- code cell 137 ---
final_dc_df  = df_october_22[df_october_22['hour'] == 18]
final_dc_df

# %% --- code cell 138 ---
dc_gdf = gpd.GeoDataFrame(
    final_dc_df,
    geometry=gpd.points_from_xy(final_dc_df['ORIGIN_BLOCK_LONGITUDE'], final_dc_df['ORIGIN_BLOCK_LATITUDE']),
    crs=4326
)
dc_gdf

# %% --- code cell 139 ---
zones = db.execute_query_to_geopandas("SELECT * FROM zones WHERE type = 3")
zones

# %% --- code cell 140 ---
joined = dc_gdf.sjoin(zones, how='inner')
joined

# %% --- code cell 141 ---
pre_dest_join = gpd.GeoDataFrame(
    joined[['OBJECTID', 'id', 'ORIGINDATETIME_TR', 'DESTINATIONDATETIME_TR']],
    geometry=gpd.points_from_xy(joined['DESTINATION_BLOCK_LONG'], joined['DESTINATION_BLOCK_LAT']),
    crs=4326
)
pre_dest_join.rename(columns={'id': 'origin'}, inplace=True)
pre_dest_join

# %% --- code cell 142 ---
sec_joined = pre_dest_join.sjoin(zones, how='left')
sec_joined

# %% --- code cell 143 ---
demand_import = sec_joined[['origin', 'id', 'ORIGINDATETIME_TR', 'DESTINATIONDATETIME_TR']]
demand_import.rename(columns={'ORIGINDATETIME_TR': 'origin_time', 'DESTINATIONDATETIME_TR': 'destination_time', 'id': 'destination'}, inplace=True)
demand_import['dataset'] = 7
demand_import

# %% --- code cell 144 ---
db.dataframe_to_db_table(demand_import, 'demand')

# %% --- code cell 145 ---


# %% [markdown] --- cell 146 ---
# ## Zones

# %% --- code cell 147 ---
zones = pd.read_csv("D:/AIC backup data/demand/Washington DC/Block_Centroids.csv")
zones

# %% --- code cell 148 ---


# %% --- code cell 149 ---
zones_no_duplicates = zones.drop_duplicates(subset=['X', 'Y'])
zones_no_duplicates

# %% --- code cell 150 ---
zones_to_import = gpd.GeoDataFrame(
    zones_no_duplicates[['MARID', 'BLOCKNAME']],
    geometry=gpd.points_from_xy(zones_no_duplicates.X, zones_no_duplicates.Y),
    crs=4326
)
zones_to_import.rename({'MARID': 'id', 'BLOCKNAME': 'name', 'geometry': 'centroid'}, inplace=True, axis='columns')
zones_to_import.set_geometry('centroid', inplace=True)
zones_to_import

# %% --- code cell 151 ---
zones_to_import.to_postgis('address_block', db._sqlalchemy_engine, if_exists='append')

# %% --- code cell 152 ---


# %% [markdown] --- cell 153 ---
# # Prague

# %% --- code cell 154 ---
nodes_filepath = r"O:\AIC data\demand/prague_test/trips.csv"
dm_filepath = r"O:\AIC data\maps/prague.csv"
out_filepath = r"C:\Workspaces\AIC\darp-benchmark\data\instances/Amodsim/prague"

# %% --- code cell 155 ---
max_prolongation = 180
time_to_start = 120
vehicle_capacity = 4
max_group_size = 4

# %% --- code cell 156 ---
trips = pd.read_csv(nodes_filepath, delim_whitespace=True)

# %% --- code cell 157 ---
trips["time_ms"] = trips["time_ms"].apply(lambda x: round(x))

# %% --- code cell 158 ---
trips

# %% --- code cell 159 ---
try:
    os.makedirs(os.path.dirname(out_filepath))
except:
    pass
with open(out_filepath, "w") as outfile:
    outfile.write("\"{}\"\n".format(dm_filepath))
    outfile.write("{} {} {} {} {}\n".format(len(trips), max_prolongation, time_to_start, vehicle_capacity, max_group_size))

# %% --- code cell 160 ---
os.path.dirname(out_filepath)

# %% --- code cell 161 ---
trips.to_csv(out_filepath, sep=" ", header=False, mode="a")

# %% --- code cell 162 ---
from sshtunnel import SSHTunnelForwarder

# %% --- code cell 163 ---
ssh_server = SSHTunnelForwarder(
            'its.fel.cvut.cz',
            ssh_username='fiedler',
            ssh_pkey='C:/Keystore/cvut',
            ssh_private_key_password='738276596949',
            remote_bind_address=('localhost', 5432),
            local_bind_address=('localhost', 1112)
        )
ssh_server.start()
port = ssh_server.local_bind_port
port

# %% --- code cell 164 ---
ssh_server.restart()
port = ssh_server.local_bind_port
port

# %% --- code cell 165 ---
