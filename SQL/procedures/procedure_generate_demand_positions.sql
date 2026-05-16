CREATE OR REPLACE PROCEDURE generate_demand_positions(
    IN p_area_id smallint,
    IN p_demand_dataset_ids integer[],
    IN p_trip_location_set_id integer DEFAULT NULL,
    IN p_trip_location_set_description varchar DEFAULT NULL,
    IN p_start_time timestamp DEFAULT NULL,
    IN p_end_time timestamp DEFAULT NULL,
    IN p_zone_types smallint[] DEFAULT NULL,
    IN p_ignored_zones bigint[] DEFAULT NULL
)
LANGUAGE plpgsql
AS
$$
DECLARE
    v_trip_location_set_id integer;
    v_in_area_trip_count bigint;
    v_existing_location_count bigint;
    v_missing_count integer;
    v_inserted_count bigint;
BEGIN
    IF p_demand_dataset_ids IS NULL OR cardinality(p_demand_dataset_ids) = 0 THEN
        RAISE EXCEPTION 'p_demand_dataset_ids must contain at least one dataset id.';
    END IF;

    IF p_start_time IS NOT NULL AND p_end_time IS NOT NULL AND p_start_time > p_end_time THEN
        RAISE EXCEPTION 'p_start_time (%) must be before or equal to p_end_time (%).', p_start_time, p_end_time;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM areas WHERE id = p_area_id) THEN
        RAISE EXCEPTION 'areas.id=% does not exist.', p_area_id;
    END IF;

    v_trip_location_set_id := resolve_trip_location_set(
        p_trip_location_set_id,
        p_trip_location_set_description
    );
    RAISE NOTICE 'Using trip_location_sets.id=%.', v_trip_location_set_id;

    CALL create_demand_sampling_edges(p_area_id);

    CALL create_selected_demand(p_demand_dataset_ids, p_start_time, p_end_time, p_ignored_zones);

    PERFORM validate_selected_demand_zones(p_zone_types);

    CALL create_zones_in_area(p_area_id, p_zone_types);

    CALL create_selected_demand_in_area();

    SELECT count(1) INTO v_in_area_trip_count FROM selected_demand_in_area;

    SELECT count(1)
    INTO v_existing_location_count
    FROM trip_locations
    JOIN selected_demand_in_area
        ON trip_locations.request_id = selected_demand_in_area.id
        AND trip_locations.set = v_trip_location_set_id;

    IF v_existing_location_count > 0 THEN
        RAISE EXCEPTION '% trip_locations rows already exist for trip_location_sets.id=% and the selected in-area demand.',
            v_existing_location_count, v_trip_location_set_id;
    END IF;

    v_missing_count := count_used_zones_without_nodes();

    IF v_missing_count > 0 THEN
        v_inserted_count := sample_demand_positions_with_neighborhood(
            p_area_id,
            v_trip_location_set_id,
            v_in_area_trip_count
        );
    ELSE
        INSERT INTO trip_locations(request_id, origin, destination, set)
        SELECT
            selected_demand_in_area.id,
            origin_nodes.node_id AS origin,
            destination_nodes.node_id AS destination,
            v_trip_location_set_id AS set
        FROM selected_demand_in_area
        JOIN LATERAL (
            SELECT demand_sampling_edges."from" AS node_id
            FROM demand_sampling_edges
            WHERE st_intersects(selected_demand_in_area.origin_zone_geom, demand_sampling_edges.geom)
            ORDER BY random()
            LIMIT 1
        ) AS origin_nodes ON TRUE
        JOIN LATERAL (
            SELECT demand_sampling_edges."from" AS node_id
            FROM demand_sampling_edges
            WHERE st_intersects(selected_demand_in_area.destination_zone_geom, demand_sampling_edges.geom)
            ORDER BY random()
            LIMIT 1
        ) AS destination_nodes ON TRUE;

        GET DIAGNOSTICS v_inserted_count = ROW_COUNT;

        IF v_inserted_count <> v_in_area_trip_count THEN
            RAISE EXCEPTION 'Inserted % trip_locations rows, but % in-area demand requests were selected.',
                v_inserted_count, v_in_area_trip_count;
        END IF;
    END IF;

    RAISE NOTICE 'Inserted % trip_locations rows for trip_location_sets.id=%.', v_inserted_count, v_trip_location_set_id;

    DROP TABLE IF EXISTS selected_demand_in_area;
    DROP TABLE IF EXISTS selected_demand;
    DROP TABLE IF EXISTS zones_in_area;
    DROP TABLE IF EXISTS demand_sampling_edges;
END;
$$;
