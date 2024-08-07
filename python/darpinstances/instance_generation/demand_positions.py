import logging
from typing import List, Optional

from roadgraphtool.db import db


# # CONFIG
# demand_datasets = [2, 3, 4, 5]
# start_time = '2022-03-11 18:00:00'
# end_time = '2022-03-11 18:59:59'
# zone_types = [2]
# trip_location_set = 1

# e.g. for zones in NYC representing trips outside the city borders (264, 265) and the Newark airport which is outside
# city borders (1)
# ignored_zones = [1, 264, 265]


def generate_positions(
        area_id: int,
        demand_datasets: List[int],
        start_time: str,
        end_time: str,
        zone_types: List[int],
        trip_location_set: int,
        ignored_zones: Optional[List[int]] = None,
        print_sql: bool = False
):
    logging.info("Selecting demand edges for target area")

    # select network network_edges
    drop_network_edges()
    sql = f"""
    CREATE TEMPORARY TABLE network_edges AS (
        SELECT
            edges."from",
            edges.geom
        FROM
            edges
        JOIN (SELECT * FROM select_network_nodes_in_area({area_id}::smallint)) from_nodes ON 
            edges.area = {area_id}
            AND edges."from" = from_nodes.id
--         JOIN nodes to_nodes ON network_edges."to" = to_nodes.id
        JOIN nodes_ways from_node_ways ON from_nodes.id = from_node_ways.node_id
        JOIN ways ON from_node_ways.way_id = ways.id
        WHERE tags->'highway' NOT IN('motorway', 'motorway_link', 'trunk', 'trunk_link')
    );
    CREATE INDEX network_edges_geom_idx ON network_edges USING GIST(geom);
    """
    if print_sql:
        logging.info(sql)

    db.execute_sql(sql)
    
    # dataset names
    demand_set_str = ', '.join((str(did) for did in demand_datasets))
    sql = f"""
    SELECT name from dataset WHERE id IN ({demand_set_str})
    """
    demand_datasets = db.execute_query_to_pandas(sql)
    logging.info(
        f"Positions will be generated for the following demand datasets: [{', '.join(demand_datasets['name'])}]")

    # zone names
    zone_type_str = ', '.join((str(zt) for zt in zone_types))
    sql = f"""
    SELECT name from zone_type WHERE id IN ({zone_type_str})
    """
    zone_types = db.execute_query_to_pandas(sql)
    logging.info(f"Demand will be joined to zones from the following zones types: [{', '.join(zone_types['name'])}]")

    sql_base = f"""
    FROM demand
        WHERE dataset IN({demand_set_str})
            AND origin_time BETWEEN '{start_time}' AND '{end_time}'
    """
    if ignored_zones:
        ignored_zones_str = ", ".join(str(zone_id) for zone_id in ignored_zones)
        logging.info(f"The following zones will be ignored: {ignored_zones_str}")
        sql_base = f"""
            {sql_base}
            AND origin NOT IN ({ignored_zones_str})
            AND destination NOT IN ({ignored_zones_str})
        """

    # trip count
    count_sql = f"""
    SELECT COUNT(1)
        {sql_base}
    """

    if print_sql:
        logging.info(count_sql)

    trip_count = db.execute_count_query(count_sql)
    logging.info(f"There are {trip_count} trips between {start_time} and {end_time} in the requested demand datasets")

    # joining trip to zones
    logging.info("Checking that all trips have a corresponding zone")

    with_sql = f"""
    WITH selected_demand AS (
        SELECT *
        {sql_base}
    )"""
    count_joint_zones_sql = f"""
    {with_sql}
    
    SELECT COUNT(1)
        FROM selected_demand
        JOIN zones AS oz ON selected_demand.origin = oz.id AND oz.type IN ({zone_type_str})
        JOIN zones AS dz ON selected_demand.destination = dz.id AND dz.type IN ({zone_type_str})
    """

    if print_sql:
        logging.info(count_joint_zones_sql)

    count_joint = db.execute_count_query(count_joint_zones_sql)

    if count_joint != trip_count:
        logging.error(f"Joining trip to zones failed! {trip_count - count_joint} trips could not be matched.")
        logging.info("Querying zone IDs with no corresponding zones")
        sql = f"""
        {with_sql}
        
        SELECT selected_demand.origin AS zone_id
        FROM selected_demand
            LEFT JOIN zones AS oz ON selected_demand.origin = oz.id AND oz.type IN ({zone_type_str})
        WHERE oz.id IS NULL
        UNION
        SELECT selected_demand.destination AS zone_id
        FROM selected_demand
            LEFT JOIN zones AS dz ON selected_demand.destination = dz.id AND dz.type IN ({zone_type_str})
        WHERE dz.id IS NULL
        """
        missing = db.execute_query_to_pandas(sql)

        logging.info("The following IDs does not have a corresponding zone: ")
        print(missing['zone_id'].to_string(index=False))

        return

    # checking zones outside the selected area
    logging.info("Counting zones and requests outside the selected area")
    counts_outside_area_sql = f"""
    {with_sql}
    SELECT count(DISTINCT zone_id) AS zone_count, count(DISTINCT request_id) AS request_count FROM (
        SELECT oz.id AS zone_id, selected_demand.id AS request_id
            FROM selected_demand
            {_get_zone_join(zone_type_str, area_id, True, True)}
        WHERE origin_areas.id IS NULL 
        UNION
        SELECT dz.id AS zone_id, selected_demand.id AS request_id
            FROM selected_demand
            {_get_zone_join(zone_type_str, area_id, False, True)}
        WHERE destination_areas.id IS NULL
    ) AS outside
    """
    counts_outside_area = db.execute_sql_and_fetch_all_rows(counts_outside_area_sql)
    if counts_outside_area[0][0] > 0:
        logging.info("%s zones will be ignored because they are outside the selected area", counts_outside_area[0][0])
        logging.info("%s requests will be ignored because they are outside the selected area", counts_outside_area[0][1])

    # joining nodes
    logging.info("Checking that all used zones contains at least one demand edge")
    zones_with_missing_nodes_sql = f"""
        {with_sql}
        SELECT oz.id AS zone
        FROM selected_demand
            {_get_zone_join(zone_type_str, area_id)}
            {_get_node_lateral_join()}
        WHERE origin_nodes.node_id IS NULL
        UNION
        SELECT dz.id AS zone
        FROM selected_demand
            {_get_zone_join(zone_type_str, area_id, False)}
            {_get_node_lateral_join(origin=False)}
        WHERE destination_nodes.node_id IS NULL
    """

    if print_sql:
        logging.info(zones_with_missing_nodes_sql)

    zones_with_missing_nodes = db.execute_query_to_pandas(zones_with_missing_nodes_sql)

    missing_count = len(zones_with_missing_nodes)
    threshold = 10

    if missing_count > threshold:
        logging.error(
            f"Joining zones to nodes failed! {missing_count} zones have no matching nodes. (max tolerated: {threshold})")
        # logging.info(count_zones_with_missing_nodes_sql)
        logging.info("The following zones does not have a corresponding node: %s", zones_with_missing_nodes['zone'].to_string(index=False))
        return

    from_sql = f"""
    FROM selected_demand
        {_get_zone_join(zone_type_str, area_id)}
        {_get_zone_join(zone_type_str, area_id, False)}
    """

    if missing_count > 0:
        logging.info(
            f"{missing_count} used zones has no corresponding network_edges. Searching neighborhood zones")

        count_nbr_sql = f"""
        {with_sql}
    
        SELECT COUNT(1)
            {from_sql}
            {_get_node_lateral_join()}
            {_get_node_lateral_join(origin=False)}
            LEFT JOIN LATERAL (
                SELECT network_edges."from" AS node_id
                FROM zones
                    JOIN areas ON areas.id = {area_id} AND st_intersects(zones.geom, areas.geom)
                    JOIN network_edges ON st_intersects(zones.geom, network_edges.geom)
                WHERE st_intersects(zones.geom, oz.geom)
                LIMIT 1
            ) AS origin_neighborhood_nodes ON TRUE
            LEFT JOIN LATERAL (
                SELECT network_edges."from" AS node_id
                FROM zones
                    JOIN areas ON areas.id = {area_id} AND st_intersects(zones.geom, areas.geom)
                    JOIN network_edges ON st_intersects(zones.geom, network_edges.geom)
                WHERE st_intersects(zones.geom, dz.geom)
                LIMIT 1
            ) AS destination_neighborhood_nodes ON TRUE
            WHERE (origin_nodes.node_id IS NOT NULL	OR origin_neighborhood_nodes.node_id IS NOT NULL)
                AND (destination_nodes.node_id IS NOT NULL OR destination_neighborhood_nodes.node_id IS NOT NULL) 
        """
        count_joint_nbr_nodes = db.execute_count_query(count_nbr_sql)

        if count_joint_nbr_nodes != trip_count:
            logging.error(
                f"Joining failed even for neighborhood zones. {trip_count - count_joint_nbr_nodes} zones have no matching nodes.")
            logging.info(f"Quering zones with missing nodes")
            sql = f"""
            {with_sql}
            SELECT origin as zone_id
            FROM selected_demand
                {_get_zone_join(zone_type_str, area_id)}
                LEFT JOIN LATERAL (
                    SELECT "from" as node_id
                    FROM network_edges
                    WHERE st_intersects(oz.geom, network_edges.geom)
                    LIMIT 1
                ) as origin_nodes ON TRUE
                LEFT JOIN LATERAL (
                    SELECT network_edges."from" AS node_id
                    FROM zones
                        JOIN network_edges ON st_intersects(zones.geom, network_edges.geom)
                    WHERE st_intersects(zones.geom, oz.geom)
                    LIMIT 1
                ) AS origin_neighborhood_nodes ON TRUE
            WHERE origin_nodes.node_id IS NULL	AND origin_neighborhood_nodes.node_id IS NULL
            UNION
            SELECT destination AS zone_id
            FROM selected_demand
                {_get_zone_join(zone_type_str, area_id, False)}
                LEFT JOIN LATERAL (
                    SELECT "from" as node_id
                    FROM network_edges
                    WHERE st_intersects(dz.geom, network_edges.geom)
                    LIMIT 1
                ) as destination_nodes ON TRUE
                LEFT JOIN LATERAL (
                    SELECT network_edges."from" AS node_id
                    FROM zones
                        JOIN network_edges ON st_intersects(zones.geom, network_edges.geom)
                    WHERE st_intersects(zones.geom, dz.geom)
                    LIMIT 1
                ) AS destination_neighborhood_nodes ON TRUE
            WHERE destination_nodes.node_id IS NULL AND destination_neighborhood_nodes.node_id IS NULL
            """
            missing = db.execute_query_to_pandas(sql)
            logging.info("The following zones does not have corresponding nodes even in the neighborhood zones")
            print(missing['zone_id'].to_string(index=False))
            exit(-1)

        # position generation
        logging.info("Inserting new node positions with usage of neighborhood zones for missing values")
        insert_sql = f"""
        INSERT INTO trip_locations(request_id, origin, destination, set)
        
        {with_sql}
        
        SELECT
            selected_demand.id,
            coalesce(origin_nodes.node_id, origin_neighborhood_nodes.node_id) as origin,
            coalesce(destination_nodes.node_id, destination_neighborhood_nodes.node_id) as destination,
            {trip_location_set} AS set
        {from_sql}
            {_get_node_lateral_join(order=True)}
            {_get_node_lateral_join(origin=False, order=True)}
            LEFT JOIN LATERAL (
                SELECT network_edges."from" AS node_id
                FROM zones
                    JOIN network_edges ON st_intersects(zones.geom, network_edges.geom)
                WHERE st_intersects(zones.geom, oz.geom)
                ORDER BY random()
                LIMIT 1
            ) AS origin_neighborhood_nodes ON TRUE
            LEFT JOIN LATERAL (
                SELECT network_edges."from" AS node_id
                FROM zones
                    JOIN network_edges ON st_intersects(zones.geom, network_edges.geom)
                WHERE st_intersects(zones.geom, dz.geom)
                ORDER BY random()
                LIMIT 1
            ) AS destination_neighborhood_nodes ON TRUE
        """

        if print_sql:
            logging.info(insert_sql)

        db.execute_sql(insert_sql)

    else:
        # position generation
        logging.info("Inserting new node positions")
        insert_sql = f"""
        INSERT INTO trip_locations(request_id, origin, destination, set)
        
        {with_sql}
        
        SELECT
            selected_demand.id,
            origin_nodes.node_id as origin,
            destination_nodes.node_id as destination,
            {trip_location_set}
        {from_sql}
            {_get_node_lateral_join(order=True)}
            {_get_node_lateral_join(origin=False, order=True)}
        """

        if print_sql:
            logging.info(insert_sql)

        db.execute_sql(insert_sql)

    # drop temporary network edges table
    drop_network_edges()


def _get_node_lateral_join(origin:bool = True, order: bool = False) -> str:
    sql = f"""
    LEFT JOIN LATERAL (
        SELECT "from" AS node_id
        FROM network_edges
        WHERE st_intersects({'oz' if origin else 'dz'}.geom, network_edges.geom)
        {'ORDER BY random()' if order else ''}
        LIMIT 1
    ) AS {'origin' if origin else 'destination'}_nodes ON TRUE
    """
    return sql


def _get_zone_join(zone_type_str: str, area_id: int, origin: bool = True, left: bool = False) -> str:
    zone_alias = 'oz' if origin else 'dz'
    areas_alias = 'origin_areas' if origin else 'destination_areas'

    sql = f"""
    JOIN zones AS {'oz' if origin else 'dz'} 
        ON {'selected_demand.origin' if origin else 'selected_demand.destination'} = {zone_alias}.id
        AND {zone_alias}.type IN ({zone_type_str})
    {"LEFT " if left else ""}JOIN areas {areas_alias} 
        ON {areas_alias}.id = {area_id}
        AND st_intersects({areas_alias}.geom, {zone_alias}.geom)
    """
    return sql

def drop_network_edges():
    # drop temporary network edges table
    sql = f"""
    DROP TABLE IF EXISTS network_edges;
    """
    db.execute_sql(sql)
