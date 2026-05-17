CREATE OR REPLACE FUNCTION select_demand_for_export(
    IN p_area_id smallint,
    IN p_demand_dataset_ids integer[],
    IN p_trip_location_set_id integer,
    IN p_trip_time_set_ids integer[] DEFAULT NULL,
    IN p_start_time timestamp DEFAULT NULL,
    IN p_end_time timestamp DEFAULT NULL
)
RETURNS TABLE (
    request_id integer,
    request_time timestamp,
    origin_db_id bigint,
    destination_db_id bigint
)
LANGUAGE plpgsql
AS
$$
BEGIN
    IF p_area_id IS NULL THEN
        RAISE EXCEPTION 'p_area_id must be provided.';
    END IF;

    IF p_trip_location_set_id IS NULL THEN
        RAISE EXCEPTION 'p_trip_location_set_id must be provided.';
    END IF;

    IF p_start_time IS NOT NULL AND p_end_time IS NOT NULL AND p_start_time > p_end_time THEN
        RAISE EXCEPTION 'p_start_time (%) must be before or equal to p_end_time (%).',
            p_start_time, p_end_time;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM areas WHERE id = p_area_id) THEN
        RAISE EXCEPTION 'areas.id=% does not exist.', p_area_id;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM trip_location_sets WHERE id = p_trip_location_set_id) THEN
        RAISE EXCEPTION 'trip_location_sets.id=% does not exist.', p_trip_location_set_id;
    END IF;

    IF p_trip_time_set_ids IS NOT NULL AND cardinality(p_trip_time_set_ids) > 0 THEN
        RETURN QUERY
        SELECT
            demand.id AS request_id,
            trip_times."time" AS request_time,
            trip_locations.origin AS origin_db_id,
            trip_locations.destination AS destination_db_id
        FROM demand
        JOIN trip_locations
            ON trip_locations.request_id = demand.id
            AND trip_locations.set = p_trip_location_set_id
        JOIN trip_times
            ON trip_times.request_id = demand.id
            AND trip_times.set = ANY(p_trip_time_set_ids)
        JOIN nodes AS origin_nodes
            ON origin_nodes.id = trip_locations.origin
        JOIN nodes AS destination_nodes
            ON destination_nodes.id = trip_locations.destination
            AND destination_nodes.id != origin_nodes.id
        JOIN areas
            ON areas.id = p_area_id
            AND st_within(origin_nodes.geom, areas.geom)
            AND st_within(destination_nodes.geom, areas.geom)
        WHERE (
                p_demand_dataset_ids IS NULL
                OR cardinality(p_demand_dataset_ids) = 0
                OR demand.dataset = ANY(p_demand_dataset_ids)
            )
            AND (p_start_time IS NULL OR trip_times."time" >= p_start_time)
            AND (p_end_time IS NULL OR trip_times."time" <= p_end_time)
        ORDER BY trip_times."time", demand.id;
    ELSE
        RETURN QUERY
        SELECT
            demand.id AS request_id,
            demand.origin_time AS request_time,
            trip_locations.origin AS origin_db_id,
            trip_locations.destination AS destination_db_id
        FROM demand
        JOIN trip_locations
            ON trip_locations.request_id = demand.id
            AND trip_locations.set = p_trip_location_set_id
        JOIN nodes AS origin_nodes
            ON origin_nodes.id = trip_locations.origin
        JOIN nodes AS destination_nodes
            ON destination_nodes.id = trip_locations.destination
            AND destination_nodes.id != origin_nodes.id
        JOIN areas
            ON areas.id = p_area_id
            AND st_within(origin_nodes.geom, areas.geom)
            AND st_within(destination_nodes.geom, areas.geom)
        WHERE (
                p_demand_dataset_ids IS NULL
                OR cardinality(p_demand_dataset_ids) = 0
                OR demand.dataset = ANY(p_demand_dataset_ids)
            )
            AND demand.origin_time IS NOT NULL
            AND (p_start_time IS NULL OR demand.origin_time >= p_start_time)
            AND (p_end_time IS NULL OR demand.origin_time <= p_end_time)
        ORDER BY demand.origin_time, demand.id;
    END IF;
END;
$$;
