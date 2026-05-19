CREATE OR REPLACE FUNCTION select_vehicle_starts_for_export(
    IN p_area_id smallint,
    IN p_demand_dataset_ids integer[] DEFAULT NULL,
    IN p_trip_location_set_id integer DEFAULT NULL,
    IN p_trip_time_set_ids integer[] DEFAULT NULL,
    IN p_start_time timestamp DEFAULT NULL,
    IN p_end_time timestamp DEFAULT NULL,
    IN p_zone_types smallint[] DEFAULT NULL,
    IN p_vehicle_count integer DEFAULT NULL,
    IN p_vehicle_to_request_ratio real DEFAULT NULL,
    IN p_random_seed real DEFAULT 0.123
)
RETURNS TABLE (
    vehicle_index integer,
    origin_db_id bigint
)
LANGUAGE plpgsql
AS
$$
DECLARE
    v_zone_count bigint;
    v_ambiguous_zone_ids bigint[];
    v_selected_request_count bigint;
    v_vehicle_count integer;
    v_sampling_edge_count bigint;
    v_missing_request_count bigint;
    v_missing_ratio numeric;
    v_missing_zone_ids bigint[];
    v_usable_zone_count bigint;
    v_missing_threshold_ratio numeric := 0.10;
    v_min_zone_area_overlap numeric := 0.50;
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

    IF p_vehicle_count IS NULL AND p_vehicle_to_request_ratio IS NULL THEN
        RAISE EXCEPTION 'Either p_vehicle_count or p_vehicle_to_request_ratio must be provided.';
    END IF;

    IF p_vehicle_count IS NOT NULL AND p_vehicle_count <= 0 THEN
        RAISE EXCEPTION 'p_vehicle_count must be positive when provided. Got %.', p_vehicle_count;
    END IF;

    IF p_vehicle_to_request_ratio IS NOT NULL AND p_vehicle_to_request_ratio <= 0 THEN
        RAISE EXCEPTION 'p_vehicle_to_request_ratio must be positive when provided. Got %.',
            p_vehicle_to_request_ratio;
    END IF;

    IF p_random_seed IS NOT NULL AND (p_random_seed < -1 OR p_random_seed > 1) THEN
        RAISE EXCEPTION 'p_random_seed must be between -1 and 1. Got %.', p_random_seed;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM areas WHERE id = p_area_id) THEN
        RAISE EXCEPTION 'areas.id=% does not exist.', p_area_id;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM trip_location_sets WHERE id = p_trip_location_set_id) THEN
        RAISE EXCEPTION 'trip_location_sets.id=% does not exist.', p_trip_location_set_id;
    END IF;

    IF p_trip_time_set_ids IS NOT NULL AND cardinality(p_trip_time_set_ids) > 0 THEN
        IF EXISTS (
            SELECT 1
            FROM unnest(p_trip_time_set_ids) AS set_ids(id)
            LEFT JOIN trip_time_sets ON trip_time_sets.id = set_ids.id
            WHERE trip_time_sets.id IS NULL
        ) THEN
            RAISE EXCEPTION 'At least one p_trip_time_set_ids value does not exist: %.',
                p_trip_time_set_ids;
        END IF;
    END IF;

    IF p_random_seed IS NOT NULL THEN
        PERFORM setseed(p_random_seed::double precision);
    END IF;

    DROP TABLE IF EXISTS pg_temp.vehicle_zones_in_area;
    DROP TABLE IF EXISTS pg_temp.selected_vehicle_demand;
    DROP TABLE IF EXISTS pg_temp.vehicle_sampling_edges;
    DROP TABLE IF EXISTS pg_temp.vehicle_candidate_nodes;

    RAISE NOTICE 'Creating vehicle zones in area table for area % with minimum zone overlap %',
        p_area_id, v_min_zone_area_overlap;

    CREATE TEMPORARY TABLE vehicle_zones_in_area ON COMMIT DROP AS
    SELECT
        zones.id,
        zones.type,
        zones.geom
    FROM zones
    JOIN areas
        ON areas.id = p_area_id
        AND st_intersects(areas.geom, zones.geom)
        AND (
            p_zone_types IS NULL
            OR cardinality(p_zone_types) = 0
            OR zones.type = ANY(p_zone_types)
        )
        AND (
            st_area(st_intersection(areas.geom, zones.geom)::geography)
            / NULLIF(st_area(zones.geom::geography), 0)
        ) >= v_min_zone_area_overlap;

    SELECT count(1) INTO v_zone_count FROM vehicle_zones_in_area;
    IF v_zone_count = 0 THEN
        RAISE EXCEPTION 'No zones found in area % for vehicle generation.', p_area_id;
    END IF;

    SELECT array_agg(id ORDER BY id)
    INTO v_ambiguous_zone_ids
    FROM (
        SELECT id
        FROM vehicle_zones_in_area
        GROUP BY id
        HAVING count(1) > 1
    ) AS ambiguous_zones;

    IF v_ambiguous_zone_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Some zone ids match more than one zone. Pass a narrower p_zone_types array. Ambiguous zone ids: %.',
            v_ambiguous_zone_ids;
    END IF;

    CREATE INDEX vehicle_zones_in_area_id_idx ON vehicle_zones_in_area(id);
    CREATE INDEX vehicle_zones_in_area_geom_idx ON vehicle_zones_in_area USING GIST(geom);
    ANALYZE vehicle_zones_in_area;

    RAISE NOTICE 'Selecting demand for vehicle origin-zone weighting.';

    IF p_trip_time_set_ids IS NOT NULL AND cardinality(p_trip_time_set_ids) > 0 THEN
        CREATE TEMPORARY TABLE selected_vehicle_demand ON COMMIT DROP AS
        SELECT
            demand.id AS request_id,
            demand.origin AS origin_zone_id
        FROM demand
        JOIN trip_locations
            ON trip_locations.request_id = demand.id
            AND trip_locations.set = p_trip_location_set_id
        JOIN trip_times
            ON trip_times.request_id = demand.id
            AND trip_times.set = ANY(p_trip_time_set_ids)
        JOIN vehicle_zones_in_area AS origin_zones
            ON origin_zones.id = demand.origin
        JOIN vehicle_zones_in_area AS destination_zones
            ON destination_zones.id = demand.destination
        WHERE (
                p_demand_dataset_ids IS NULL
                OR cardinality(p_demand_dataset_ids) = 0
                OR demand.dataset = ANY(p_demand_dataset_ids)
            )
            AND (p_start_time IS NULL OR trip_times."time" >= p_start_time)
            AND (p_end_time IS NULL OR trip_times."time" <= p_end_time);
    ELSE
        CREATE TEMPORARY TABLE selected_vehicle_demand ON COMMIT DROP AS
        SELECT
            demand.id AS request_id,
            demand.origin AS origin_zone_id
        FROM demand
        JOIN trip_locations
            ON trip_locations.request_id = demand.id
            AND trip_locations.set = p_trip_location_set_id
        JOIN vehicle_zones_in_area AS origin_zones
            ON origin_zones.id = demand.origin
        JOIN vehicle_zones_in_area AS destination_zones
            ON destination_zones.id = demand.destination
        WHERE (
                p_demand_dataset_ids IS NULL
                OR cardinality(p_demand_dataset_ids) = 0
                OR demand.dataset = ANY(p_demand_dataset_ids)
            )
            AND demand.origin_time IS NOT NULL
            AND (p_start_time IS NULL OR demand.origin_time >= p_start_time)
            AND (p_end_time IS NULL OR demand.origin_time <= p_end_time);
    END IF;

    SELECT count(1) INTO v_selected_request_count FROM selected_vehicle_demand;
    IF v_selected_request_count = 0 THEN
        RAISE EXCEPTION 'No selected demand found for vehicle generation.';
    END IF;

    IF p_vehicle_count IS NOT NULL THEN
        v_vehicle_count := p_vehicle_count;
    ELSE
        v_vehicle_count := ceil(v_selected_request_count::double precision * p_vehicle_to_request_ratio)::integer;
    END IF;

    IF v_vehicle_count <= 0 THEN
        RAISE EXCEPTION 'Resolved vehicle count must be positive. Got %.', v_vehicle_count;
    END IF;

    RAISE NOTICE 'Selected % requests for vehicle generation. Sampling % vehicles.',
        v_selected_request_count, v_vehicle_count;

    RAISE NOTICE 'Creating vehicle sampling edges table for area %.', p_area_id;

    CREATE TEMPORARY TABLE vehicle_sampling_edges ON COMMIT DROP AS
    SELECT DISTINCT
        edges."from" AS node_id,
        edges.geom
    FROM edges
    JOIN select_network_nodes_in_area(p_area_id) AS from_nodes
        ON edges.area = p_area_id
        AND edges."from" = from_nodes.id
    JOIN nodes_ways AS from_node_ways
        ON from_nodes.id = from_node_ways.node_id
    JOIN ways
        ON from_node_ways.way_id = ways.id
    JOIN ways_tags
        ON ways_tags.way_id = ways.id
    JOIN tags
        ON tags.id = ways_tags.tag_id
        AND tags."key" = 'highway'
    WHERE ways_tags.tag_value NOT IN ('motorway', 'motorway_link', 'trunk', 'trunk_link');

    SELECT count(1) INTO v_sampling_edge_count FROM vehicle_sampling_edges;
    IF v_sampling_edge_count = 0 THEN
        RAISE EXCEPTION 'No vehicle sampling edges found for area %.', p_area_id;
    END IF;

    CREATE INDEX vehicle_sampling_edges_geom_idx ON vehicle_sampling_edges USING GIST(geom);
    ANALYZE vehicle_sampling_edges;

    CREATE TEMPORARY TABLE vehicle_candidate_nodes ON COMMIT DROP AS
    SELECT DISTINCT
        vehicle_zones_in_area.id AS zone_id,
        vehicle_sampling_edges.node_id
    FROM vehicle_zones_in_area
    JOIN vehicle_sampling_edges
        ON st_intersects(vehicle_zones_in_area.geom, vehicle_sampling_edges.geom);

    CREATE INDEX vehicle_candidate_nodes_zone_id_idx ON vehicle_candidate_nodes(zone_id);
    ANALYZE vehicle_candidate_nodes;

    WITH origin_zone_weights AS (
        SELECT
            selected_vehicle_demand.origin_zone_id AS zone_id,
            count(1) AS request_count
        FROM selected_vehicle_demand
        GROUP BY selected_vehicle_demand.origin_zone_id
    )
    SELECT
        coalesce(sum(origin_zone_weights.request_count), 0),
        array_agg(origin_zone_weights.zone_id ORDER BY origin_zone_weights.zone_id)
    INTO v_missing_request_count, v_missing_zone_ids
    FROM origin_zone_weights
    WHERE NOT EXISTS (
        SELECT 1
        FROM vehicle_candidate_nodes
        WHERE vehicle_candidate_nodes.zone_id = origin_zone_weights.zone_id
    );

    v_missing_ratio := v_missing_request_count::numeric / v_selected_request_count::numeric;

    IF v_missing_ratio > v_missing_threshold_ratio THEN
        RAISE EXCEPTION 'Vehicle origin-zone sampling failed. Origin zones without matching road nodes cover % requests (% %% of % selected requests), above threshold 10%%. Zone ids: %.',
            v_missing_request_count,
            round(100 * v_missing_ratio, 2),
            v_selected_request_count,
            v_missing_zone_ids;
    END IF;

    IF v_missing_request_count > 0 THEN
        RAISE NOTICE 'Ignoring origin zones without matching road nodes. Affected demand: % requests (% %% of selected requests). Zone ids: %.',
            v_missing_request_count,
            round(100 * v_missing_ratio, 2),
            v_missing_zone_ids;
    END IF;

    SELECT count(1)
    INTO v_usable_zone_count
    FROM (
        SELECT selected_vehicle_demand.origin_zone_id
        FROM selected_vehicle_demand
        WHERE EXISTS (
            SELECT 1
            FROM vehicle_candidate_nodes
            WHERE vehicle_candidate_nodes.zone_id = selected_vehicle_demand.origin_zone_id
        )
        GROUP BY selected_vehicle_demand.origin_zone_id
    ) AS usable_zones;

    IF v_usable_zone_count = 0 THEN
        RAISE EXCEPTION 'No usable origin zones with matching road nodes found for vehicle generation.';
    END IF;

    RETURN QUERY
    WITH origin_zone_weights AS (
        SELECT
            selected_vehicle_demand.origin_zone_id AS zone_id,
            count(1)::bigint AS request_count
        FROM selected_vehicle_demand
        WHERE EXISTS (
            SELECT 1
            FROM vehicle_candidate_nodes
            WHERE vehicle_candidate_nodes.zone_id = selected_vehicle_demand.origin_zone_id
        )
        GROUP BY selected_vehicle_demand.origin_zone_id
    ),
    weighted_origin_zones AS (
        SELECT
            origin_zone_weights.zone_id,
            (sum(origin_zone_weights.request_count) OVER (
                ORDER BY origin_zone_weights.zone_id
            ))::double precision AS cumulative_weight,
            (sum(origin_zone_weights.request_count) OVER ())::double precision AS total_weight
        FROM origin_zone_weights
    ),
    vehicle_indices AS (
        SELECT generate_series(0, v_vehicle_count - 1) AS vehicle_index
    )
    SELECT
        vehicle_indices.vehicle_index,
        sampled_nodes.node_id AS origin_db_id
    FROM vehicle_indices
    CROSS JOIN LATERAL (
        SELECT
            random() * weighted_totals.total_weight
            + vehicle_indices.vehicle_index * 0 AS ticket
        FROM (
            SELECT max(weighted_origin_zones.total_weight) AS total_weight
            FROM weighted_origin_zones
        ) AS weighted_totals
    ) AS random_ticket
    JOIN LATERAL (
        SELECT weighted_origin_zones.zone_id
        FROM weighted_origin_zones
        WHERE weighted_origin_zones.cumulative_weight >= random_ticket.ticket
        ORDER BY weighted_origin_zones.cumulative_weight
        LIMIT 1
    ) AS sampled_zones ON TRUE
    JOIN LATERAL (
        SELECT vehicle_candidate_nodes.node_id
        FROM vehicle_candidate_nodes
        WHERE vehicle_candidate_nodes.zone_id = sampled_zones.zone_id
        ORDER BY random()
        LIMIT 1
    ) AS sampled_nodes ON TRUE
    ORDER BY vehicle_indices.vehicle_index;

    DROP TABLE IF EXISTS pg_temp.vehicle_candidate_nodes;
    DROP TABLE IF EXISTS pg_temp.vehicle_sampling_edges;
    DROP TABLE IF EXISTS pg_temp.selected_vehicle_demand;
    DROP TABLE IF EXISTS pg_temp.vehicle_zones_in_area;
END;
$$;
