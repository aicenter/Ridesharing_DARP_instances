# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%
# %load_ext autoreload

# %%
# %autoreload

# %%
import importlib
import roadgraphtool
importlib.reload(roadgraphtool)
import pandas as pd
import os
import matplotlib.pyplot as plt
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
import roadgraphtool.config
import roadgraphtool.db as db_module
db = db_module.db

config_path = Path(r"C:\Google Drive AIC\My Drive\AIC Experiment Data\Line Planning\Instances\LODES/config.yaml")
config = roadgraphtool.config.parse_config_file(config_path)
roadgraphtool.db.init_db(config)
roadgraphtool.config.set_logging(config)

# %% [markdown]
# # NYC Commuter Demand
# LODES-style census-block zones and OD counts. Use `import_commuter_zones` / `import_commuter_demand` with paths for another state; dataset id and zone type id stay fixed.

# %%
COMMUTER_DEMAND_DATASET_ID = 1
COMMUTER_ZONE_TYPE_ID = 1


def import_commuter_zones(census_blocks_path: Path | str) -> None:
    """Load census blocks GeoPackage/Shapefile and insert into `zones`.

    Expects GEOID20, NAME20, geometry columns (LODES / Census 2020 block fields).
    Zone ``type`` is fixed to ``COMMUTER_ZONE_TYPE_ID``.
    """
    path = Path(census_blocks_path)
    census_gdf = gpd.read_file(path)
    census_gdf_for_insert = gpd.GeoDataFrame(census_gdf[["GEOID20", "NAME20", "geometry"]])
    census_gdf_for_insert.rename(
        columns={"GEOID20": "id", "NAME20": "name", "geometry": "geom"}, inplace=True
    )
    census_gdf_for_insert["type"] = COMMUTER_ZONE_TYPE_ID
    census_gdf_for_insert.set_geometry("geom", inplace=True)
    census_gdf_for_insert.to_crs(epsg=4326, inplace=True)
    db.geodataframe_to_db_table(census_gdf_for_insert, "zones", store_index=False, chunk=True)


def import_commuter_demand(demand_csv_path: Path | str) -> None:
    """Read LODES-style OD CSV (h_geocode, w_geocode, S000), disaggregate counts, insert into `demand`.

    ``dataset`` is fixed to ``COMMUTER_DEMAND_DATASET_ID``. ``origin_time`` is fixed.
    """
    path = Path(demand_csv_path)
    demand = pd.read_csv(path)
    demand_sel = pd.DataFrame(demand[["h_geocode", "w_geocode", "S000"]])
    demand_disaggregated = demand_sel.loc[demand_sel.index.repeat(demand_sel["S000"])]
    demand_disaggregated.reset_index(drop=True, inplace=True)
    demand_for_insert = pd.DataFrame(demand_disaggregated[["h_geocode", "w_geocode"]])
    demand_for_insert.rename(
        columns={"h_geocode": "origin", "w_geocode": "destination"}, inplace=True
    )
    demand_for_insert["origin_time"] = pd.to_datetime("2026-01-01 00:08:00")
    demand_for_insert["dataset"] = COMMUTER_DEMAND_DATASET_ID
    db.dataframe_to_db_table(demand_for_insert, "demand")


# %% [markdown]
# ## Zones
# NY Census Blocks

# %%
import_commuter_zones(Path(r"C:\OwnCloud\areas\NY census blocks"))

# %% [markdown]
# ## Demand
#

# %%
import_commuter_demand(Path(r"C:\OwnCloud\demand\LODES/ny_od_main_JT00_2023.csv"))


# %% [markdown]
# # NJ Commuter Demand
# ## Zones

# %%
import_commuter_zones(Path(r"C:\OwnCloud\areas\NJ census blocks"))

# %% [markdown]
# ## NJ Demand

# %%
import_commuter_demand(Path(r"C:\OwnCloud\demand\LODES/NJ/nj_od_main_JT00_2023.csv"))

# %%
ny_zones_path = Path(r"C:\OwnCloud\areas\NY census blocks")
ny_zones = gpd.read_file(ny_zones_path)
ny_zones.iloc[0:3]

# %%
nj_zones_path = Path(r"C:\OwnCloud\areas\NJ census blocks")
nj_zones = gpd.read_file(nj_zones_path)
nj_zones.iloc[0:3]

# %% [markdown]
# # NYC

# %% [markdown]
# ## Monthly statistics

# %%
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

# %%
dfsmagg = dfsm.groupby('Month/Year').sum()
dfsmagg.sort_values('Trips Per Day', inplace=True, ascending=False)
dfsmagg

# %%
dfsmagg_from_2019 = dfsmagg[dfsmagg.index > '2019-01']
dfsmagg_from_2019

# %%
dfsmagg_from_2019_bd = dfsmagg_from_2019.sort_index()

plt.figure(figsize=(28, 5))
plt.xticks(rotation = 90)
plt.plot(dfsmagg_from_2019_bd.index, dfsmagg_from_2019_bd['Trips Per Day'])


# %% [markdown]
# ## Common

# %%
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


# %% [markdown]
# ## 2022-04

# %%
trips = nyc_import_month(Path(r"O:\Backups/AIC backup data\Demand/NYC/2022-04"), 2022, 4)
trips

# %%
for t in trips:
    print(f'importing {len(t)} trips')
    db.dataframe_to_db_table(t, 'demand')

# %%
filename = r'O:\Backups/AIC backup data\Demand/NYC/2022-04/fhvhv_tripdata_2022-04.parquet'
pq.read_table(filename).to_pandas()

# %% [markdown]
# ### Hourly Stats

# %%
sql = r"SELECT extract(hour from origin_time) AS hour, count(id) FROM demand WHERE dataset IN(2, 3, 4, 5) and date(origin_time) = '2022-04-05' GROUP BY extract(hour from origin_time)"
nyc_hourly_stats = db.execute_query_to_pandas(sql)
px.line(nyc_hourly_stats, x='hour', y='count')

# %% [markdown]
# ## Data 2022-03

# %%
# trips_y = pq.read_table(r"O:\Backups\AIC data\Demand/NYC/yellow_tripdata_2013-01.parquet")
# trips_y = pq.read_table(r"D:\AIC backup data\Demand/NYC/yellow_tripdata_2022-03.parquet")
# trips_y = pq.read_table(r"D:\AIC backup data\Demand/NYC/green_tripdata_2022-03.parquet")
# trips_y = pq.read_table(r"D:\AIC backup data\Demand/NYC/fhv_tripdata_2022-03.parquet")
trips_y = pq.read_table(r"D:\AIC backup data\Demand/NYC/fhvhv_tripdata_2022-03.parquet")
trips_y = trips_y.to_pandas()
trips_y

# %%
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

# %%
# trips_y_for_import.to_sql('demand', con, if_exists='append', index=False)
db.dataframe_to_db_table(trips_y_for_import, 'demand')

# %%

# %% [markdown]
# ### Update table

# %%
trips_y_for_import = trips_y[['PULocationID', 'DOLocationID', 'tpep_pickup_datetime', 'tpep_dropoff_datetime']]
trips_y_for_import.rename(columns={"PULocationID": "origin", "DOLocationID": "destination", "tpep_pickup_datetime": 'origin_time', "tpep_dropoff_datetime": 'destination_time'}, inplace=True)
trips_y_for_import

# %%
db.dataframe_to_db_table(trips_y_for_import, 'tmp_demand')


# %%
sql = """
    UPDATE demand
    SET destination_time = tmp_demand.destination_time
    FROM tmp_demand
    WHERE demand.origin_time = tmp_demand.origin_time
        AND demand.origin = tmp_demand.origin,
"""

# %%

# %% [markdown]
# ## Daily statistic

# %%
sql = r"SELECT date(origin_time), count(id) FROM demand WHERE dataset = 2 and origin_time between '2022-03-01' AND '2022-03-31' GROUP BY date(origin_time)"

# %%
nyc_daily_stats = db.execute_query_to_pandas(sql)
nyc_daily_stats

# %%
nyc_daily_stats

# %%
plt.figure(figsize=(25,8))
plt.plot(nyc_daily_stats['date'], nyc_daily_stats['count'])

# %%
nyc_daily_stats.sort_values('count')

# %% [markdown]
# ## Hourly statistic

# %%
sql = r"SELECT extract(hour from origin_time) AS hour, count(id) FROM demand WHERE dataset = 2 and date(origin_time) = '2022-03-11' GROUP BY extract(hour from origin_time)"
nyc_hourly_stats = db.execute_query_to_pandas(sql)
nyc_hourly_stats

# %%
plt.figure(figsize=(25,8))
plt.plot(nyc_hourly_stats['hour'], nyc_hourly_stats['count'])

# %%
nyc_hourly_stats.sort_values('count')

# %%

# %% [markdown]
# ## Zones
# NYC Taxi zones

# %%
gdf = gpd.read_file(r'D:\AIC backup data\demand\NYC\zones/geo_export_06f7643a-59de-4990-93ae-1c5671a587ba.shp')
gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
gdf

# %%
gdf_for_insert = gdf.rename(columns={"zone": "name", "geometry": "geom", 'objectid': 'id'})
gdf_for_insert.drop(['location_i', 'shape_area', 'shape_leng', 'borough'], axis=1, inplace=True)
gdf_for_insert['dataset'] = 2
gdf_for_insert['id'] = gdf_for_insert['id'].astype(int)
gdf_for_insert.set_geometry('geom', inplace=True)
gdf_for_insert["geom"] = [MultiPolygon([feature]) if isinstance(feature, Polygon) else feature for feature in gdf_for_insert["geom"]]
gdf_for_insert

# %%
gdf_for_insert.to_postgis('zones', con, if_exists='append')

# %%
gdf_for_insert.geom[0]

# %% [markdown]
# ## Fleet Size

# %%
sql = r"SELECT COUNT(id) FROM demand WHERE dataset = 2 and origin_time BETWEEN '2022-03-11 18:00' AND '2022-03-11 18:15'"
req_count = db.execute_query_to_pandas(sql)
req_count

# %%
sql = r"SELECT AVG(extract(EPOCH FROM (demand.destination_time - demand.origin_time))) AS avg_duration FROM demand WHERE dataset = 2 and origin_time BETWEEN '2022-03-11 18:00' AND '2022-03-11 18:15'"
avg_time_per_trip = db.execute_query_to_pandas(sql)
avg_time_per_trip = avg_time_per_trip.iloc[0]['avg_duration']
avg_time_per_trip

# %%
ridesharing_rate = 2 # avg vehicle occupancy. Estimated.
experiment_length = 15 # length/time horizon of the ridesharing instance

car_count = req_count / ridesharing_rate / max(experiment_length / (avg_time_per_trip / 60), 1)
car_count

# %%
experiment_length / (avg_time_per_trip / 60)

# %% [markdown]
#

# %% [markdown]
# ## Old vs new demand files

# %%
demand_path = Path(r"O:\Backups/AIC backup data\Demand\NYC")
trips_2013_01 = pd.read_parquet(demand_path / "yellow_tripdata_2013-01.parquet")
trips_2013_01

# %%
trips_2015_01 = pd.read_parquet(demand_path / "yellow_tripdata_2015-01.parquet")
trips_2015_01

# %%
trips_csv_2015_01 = pd.read_csv(demand_path / "yellow_tripdata_2015-01.csv")
trips_csv_2015_01

# %%
trips_csv_2015_01['pickup_latitude'].unique()

# %%
trips_csv_2016_03 = pd.read_csv(demand_path / "yellow_tripdata_2016-03.csv")
trips_csv_2016_03

# %%
trips_csv_2016_03['pickup_latitude'].unique()

# %%
trips_csv_2016_11 = pd.read_csv(demand_path / "yellow_tripdata_2016-11.csv")
trips_csv_2016_11

# %%
trips_csv_2016_07 = pd.read_csv(demand_path / "yellow_tripdata_2016-07.csv")
trips_csv_2016_07

# %% [markdown]
# # Chicago

# %% [markdown]
# ## Zones

# %% [markdown]
# ## Comunity areas

# %%
gdf = gpd.read_file(r'D:\AIC backup data\demand\Chicago\zones/Comunity areas/')
gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
gdf

# %%
gdf_for_insert = gdf[['geometry', 'area_num_1', 'community']]
gdf_for_insert.rename(columns={"geometry": "geom", 'area_num_1': 'id', 'community': 'name'}, inplace=True)
gdf_for_insert['dataset'] = 3
gdf_for_insert['level'] = 0
gdf_for_insert.set_geometry('geom', inplace=True)
gdf_for_insert["geom"] = [MultiPolygon([feature]) if isinstance(feature, Polygon) else feature for feature in gdf_for_insert["geom"]]
gdf_for_insert

# %%
gdf_for_insert.to_postgis('zones', con, if_exists='append')

# %%

# %% [markdown]
# ## Census Tracts

# %%
gdf = gpd.read_file(r'D:\AIC backup data\demand\Chicago\zones/Census tracts/')
gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
gdf

# %%
gdf_for_insert = gdf[['geometry', 'census_t_1']]
gdf_for_insert.rename(columns={"geometry": "geom", 'census_t_1': 'id'}, inplace=True)
gdf_for_insert['dataset'] = 3
gdf_for_insert['level'] = 1
gdf_for_insert.set_geometry('geom', inplace=True)
gdf_for_insert["geom"] = [MultiPolygon([feature]) if isinstance(feature, Polygon) else feature for feature in gdf_for_insert["geom"]]
gdf_for_insert

# %%
gdf_for_insert.to_postgis('zones', con, if_exists='append')

# %% [markdown]
# ## Censtus Tracks Illinois

# %%
gdf = gpd.read_file(r'D:\AIC backup data\demand\Illinois')
gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
gdf

# %%
gdf_for_insert = gdf[['geometry', 'GEOID']]
gdf_for_insert.rename(columns={"geometry": "geom", 'GEOID': 'id'}, inplace=True)
gdf_for_insert['type'] = 1
gdf_for_insert.set_geometry('geom', inplace=True)
gdf_for_insert["geom"] = [MultiPolygon([feature]) if isinstance(feature, Polygon) else feature for feature in gdf_for_insert["geom"]]
gdf_for_insert

# %%
meta = sqlalchemy.MetaData()
zone_table = geoalchemy2.Table('zones', meta, autoload_with=db._sqlalchemy_engine)
insert_statement = sqlalchemy.dialects.postgresql.insert(zone_table).on_conflict_do_nothing()

# %%
list_to_insert = [{'id': id, 'geom': geoalchemy2.shape.from_shape(geo, srid=4326), 'type': type} for id, geo, type in zip(gdf_for_insert.id, gdf_for_insert.geom, gdf_for_insert['type'])]
list_to_insert[0]

# %%
db._sqlalchemy_engine.execute(insert_statement, list_to_insert)

# %%
insert_statement

# %%
# gdf_for_insert.to_postgis('zones', db._sqlalchemy_engine, if_exists='append')
gdf_for_insert.to_sql('zones', db._sqlalchemy_engine, if_exists='append', method=insert_on_duplicate, dtype={'geom': geoalchemy2.Geometry('Multipolygon', srid=4326)})

# %%

# %% [markdown]
# ## Monthly statistics

# %%
sql = """
SELECT COUNT(1), DATE_TRUNC('month', origin_time) as month
FROM demand
WHERE dataset = 1
GROUP BY DATE_TRUNC('month', origin_time)
"""

# %%
monthly_stats = db.execute_query_to_pandas(sql)

# %%
monthly_stats.sort_values('month', inplace=True)
monthly_stats

# %%
px.line(monthly_stats, 'month', 'count')

# %%
monthly_stats['count']

# %% [markdown]
# ## Daily statistics

# %%
sql = """
SELECT COUNT(1), DATE_TRUNC('day', origin_time) as day
FROM demand
WHERE dataset = 1 AND origin_time BETWEEN '2022-05-01' AND '2022-05-31 23:59:59'
GROUP BY DATE_TRUNC('day', origin_time)
"""

# %%
chicago_daily_stats = db.execute_query_to_pandas(sql)

# %%
chicago_daily_stats.sort_values('day', inplace=True)
chicago_daily_stats

# %%
px.line(chicago_daily_stats, 'day', 'count')

# %% [markdown]
# ## Hourly Stats

# %%
sql = """
SELECT COUNT(1), DATE_TRUNC('hour', origin_time) as hour
FROM demand
WHERE dataset = 1 AND origin_time BETWEEN '2022-05-20 00:00:00' AND '2022-05-20 23:59:59'
GROUP BY DATE_TRUNC('hour', origin_time)
"""

# %%
chicago_hourly_stats = db.execute_query_to_pandas(sql)

# %%
chicago_hourly_stats.sort_values('hour', inplace=True)
chicago_hourly_stats

# %%
px.line(chicago_hourly_stats, 'hour', 'count')

# %% [markdown]
# ## Trip location generation

# %%
demand_datasets = [1]
start_time = '2022-05-20 18:00'
end_time = '2022-05-20 18:15'
zone_types = [1, 2]
trip_location_set = 3

# %%
demand_set_str = ', '.join((str(did) for did in demand_datasets))
zone_type_str = ', '.join((str(zt) for zt in zone_types))
sql_base = f"""
FROM demand
	WHERE dataset IN({demand_set_str})
		AND origin_time BETWEEN '{start_time}' AND '{end_time}'
"""

# %%
count_sql = f"""
SELECT COUNT(1)
	{sql_base}
"""
count = db.execute_count_query(count_sql)
count

# %%
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

# %%
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

# %%
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

# %%
db.execute_sql(insert_sql)

# %%
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

# %%
debug_nodes[debug_nodes['id'] is None]

# %%
debug_nodes.columns

# %%

# %% [markdown]
# # Washington DC

# %% [markdown]
# ## Zone load

# %%
zones = db.execute_query_to_geopandas("SELECT * FROM zones WHERE type = 4")

# %% [markdown]
# ## Common

# %%
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


# %% [markdown]
# ## 2021

# %%
# dir_path = r"D:\AIC backup data\demand\Washington DC"
dir_path = r="O:\Backups\AIC backup data\Demand\DC\OpenDataDC_Taxi_2021"
dc_df = dc_load_year(2021, Path(dir_path))
dc_df

# %% [markdown]
# ### Monthly statistics

# %%
dc_mstats = dc_df.groupby('month').size()
px.line(dc_mstats)

# %% [markdown]
# ### Daily statistics

# %%
df_october = pd.DataFrame(dc_df[dc_df['month'] == 10])
df_october['day'] = df_october['ORIGINDATETIME_TR'].dt.day
dc_dstats = df_october.groupby('day').size()
px.line(dc_dstats)

# %% [markdown]
# ### Hourly Stats

# %%
df_october_22 = pd.DataFrame(df_october[df_october['day'] == 22])
df_october_22['hour'] = df_october_22['ORIGINDATETIME_TR'].dt.hour
dc_hstats = df_october_22.groupby('hour').size()
px.line(dc_hstats)

# %% [markdown]
# ## 2022

# %%
dir_path = r="O:\Backups\AIC backup data\Demand\DC\OpenDataDC_Taxi_2022"
# dir_path = r'D:\AIC backup data\demand\Washington DC\2022'
dc_df_2022 = dc_load_year(2022, Path(dir_path))
dc_df_2022

# %% [markdown]
# ### Monthly statistics

# %%
dc_mstats = dc_df_2022.groupby('month').size()
px.line(dc_mstats)

# %% [markdown]
# ### Daily statistics

# %%
df_april = pd.DataFrame(dc_df_2022[dc_df_2022['month'] == 4])
df_april['day'] = df_april['ORIGINDATETIME_TR'].dt.day
dc_dstats = df_april.groupby('day').size()
px.line(dc_dstats)

# %% [markdown]
# ### Import

# %%
joined = join_zones(df_april)
joined

# %%
import_to_db(df_april)

# %% [markdown]
# ### Hourly Stats

# %%
df_april_5 = pd.DataFrame(df_april[df_april['day'] == 5])
df_april_5['hour'] = df_april_5['ORIGINDATETIME_TR'].dt.hour
dc_hstats = df_april_5.groupby('hour').size()
px.line(dc_hstats)

# %% [markdown]
# ## 24 h demand import

# %%

# %%
db.dataframe_to_db_table(demand_import, 'demand')

# %%
demand_db = db.execute_query_to_pandas("SELECT * FROM trip_times WHERE set = 2")
demand_db

# %%
px.histogram(demand_db['time'])

# %%

# %% [markdown]
# ## 1 hour demand

# %%
final_dc_df  = df_october_22[df_october_22['hour'] == 18]
final_dc_df

# %%
dc_gdf = gpd.GeoDataFrame(
    final_dc_df,
    geometry=gpd.points_from_xy(final_dc_df['ORIGIN_BLOCK_LONGITUDE'], final_dc_df['ORIGIN_BLOCK_LATITUDE']),
    crs=4326
)
dc_gdf

# %%
zones = db.execute_query_to_geopandas("SELECT * FROM zones WHERE type = 3")
zones

# %%
joined = dc_gdf.sjoin(zones, how='inner')
joined

# %%
pre_dest_join = gpd.GeoDataFrame(
    joined[['OBJECTID', 'id', 'ORIGINDATETIME_TR', 'DESTINATIONDATETIME_TR']],
    geometry=gpd.points_from_xy(joined['DESTINATION_BLOCK_LONG'], joined['DESTINATION_BLOCK_LAT']),
    crs=4326
)
pre_dest_join.rename(columns={'id': 'origin'}, inplace=True)
pre_dest_join

# %%
sec_joined = pre_dest_join.sjoin(zones, how='left')
sec_joined

# %%
demand_import = sec_joined[['origin', 'id', 'ORIGINDATETIME_TR', 'DESTINATIONDATETIME_TR']]
demand_import.rename(columns={'ORIGINDATETIME_TR': 'origin_time', 'DESTINATIONDATETIME_TR': 'destination_time', 'id': 'destination'}, inplace=True)
demand_import['dataset'] = 7
demand_import

# %%
db.dataframe_to_db_table(demand_import, 'demand')

# %%

# %% [markdown]
# ## Zones

# %%
zones = pd.read_csv("D:/AIC backup data/demand/Washington DC/Block_Centroids.csv")
zones

# %%

# %%
zones_no_duplicates = zones.drop_duplicates(subset=['X', 'Y'])
zones_no_duplicates

# %%
zones_to_import = gpd.GeoDataFrame(
    zones_no_duplicates[['MARID', 'BLOCKNAME']],
    geometry=gpd.points_from_xy(zones_no_duplicates.X, zones_no_duplicates.Y),
    crs=4326
)
zones_to_import.rename({'MARID': 'id', 'BLOCKNAME': 'name', 'geometry': 'centroid'}, inplace=True, axis='columns')
zones_to_import.set_geometry('centroid', inplace=True)
zones_to_import

# %%
zones_to_import.to_postgis('address_block', db._sqlalchemy_engine, if_exists='append')

# %%

# %% [markdown]
# # Prague

# %%
nodes_filepath = r"O:\AIC data\demand/prague_test/trips.csv"
dm_filepath = r"O:\AIC data\maps/prague.csv"
out_filepath = r"C:\Workspaces\AIC\darp-benchmark\data\instances/Amodsim/prague"

# %%
max_prolongation = 180
time_to_start = 120
vehicle_capacity = 4
max_group_size = 4

# %%
trips = pd.read_csv(nodes_filepath, delim_whitespace=True)

# %%
trips["time_ms"] = trips["time_ms"].apply(lambda x: round(x))

# %%
trips

# %%
try:
    os.makedirs(os.path.dirname(out_filepath))
except:
    pass
with open(out_filepath, "w") as outfile:
    outfile.write("\"{}\"\n".format(dm_filepath))
    outfile.write("{} {} {} {} {}\n".format(len(trips), max_prolongation, time_to_start, vehicle_capacity, max_group_size))

# %%
os.path.dirname(out_filepath)

# %%
trips.to_csv(out_filepath, sep=" ", header=False, mode="a")

# %%
from sshtunnel import SSHTunnelForwarder

# %%
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

# %%
ssh_server.restart()
port = ssh_server.local_bind_port
port

# %%
