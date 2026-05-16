CREATE OR REPLACE FUNCTION sample_demand_positions_with_neighborhood(
    IN p_area_id smallint,
    IN p_trip_location_set_id integer,
    IN p_in_area_request_count bigint
)
RETURNS bigint
LANGUAGE plpgsql
AS
$$
DECLARE
    matched_request_count bigint;
    unmatched_request_count bigint;
    unmatched_request_ratio numeric;
    unmatched_request_threshold_ratio numeric := 0.05;
    missing_node_zones bigint[];
    inserted_count bigint;
BEGIN
    RAISE NOTICE 'Searching neighborhood zones.';

    SELECT count(1)
    INTO matched_request_count
    FROM selected_demand_in_area
    WHERE (
        EXISTS (
            SELECT 1
            FROM demand_sampling_edges
            WHERE st_intersects(selected_demand_in_area.origin_zone_geom, demand_sampling_edges.geom)
        )
        OR EXISTS (
            SELECT 1
            FROM zones
            JOIN areas
                ON areas.id = p_area_id
                AND st_intersects(zones.geom, areas.geom)
            JOIN demand_sampling_edges
                ON st_intersects(zones.geom, demand_sampling_edges.geom)
            WHERE st_intersects(zones.geom, selected_demand_in_area.origin_zone_geom)
        )
    )
    AND (
        EXISTS (
            SELECT 1
            FROM demand_sampling_edges
            WHERE st_intersects(selected_demand_in_area.destination_zone_geom, demand_sampling_edges.geom)
        )
        OR EXISTS (
            SELECT 1
            FROM zones
            JOIN areas
                ON areas.id = p_area_id
                AND st_intersects(zones.geom, areas.geom)
            JOIN demand_sampling_edges
                ON st_intersects(zones.geom, demand_sampling_edges.geom)
            WHERE st_intersects(zones.geom, selected_demand_in_area.destination_zone_geom)
        )
    );

    unmatched_request_count := p_in_area_request_count - matched_request_count;


    IF unmatched_request_count > 0 THEN

        RAISE NOTICE '% in-area requests not matched even in neighborhood zones. Analyzing the problematic zones.', unmatched_request_count;

        SELECT array_agg(zone_id ORDER BY zone_id)
        INTO missing_node_zones
        FROM (
            SELECT DISTINCT origin_zone_id AS zone_id
            FROM selected_demand_in_area
            WHERE NOT EXISTS (
                SELECT 1
                FROM demand_sampling_edges
                WHERE st_intersects(selected_demand_in_area.origin_zone_geom, demand_sampling_edges.geom)
            )
            AND NOT EXISTS (
                SELECT 1
                FROM zones
                JOIN areas
                    ON areas.id = p_area_id
                    AND st_intersects(zones.geom, areas.geom)
                JOIN demand_sampling_edges
                    ON st_intersects(zones.geom, demand_sampling_edges.geom)
                WHERE st_intersects(zones.geom, selected_demand_in_area.origin_zone_geom)
            )
            UNION
            SELECT DISTINCT destination_zone_id AS zone_id
            FROM selected_demand_in_area
            WHERE NOT EXISTS (
                SELECT 1
                FROM demand_sampling_edges
                WHERE st_intersects(selected_demand_in_area.destination_zone_geom, demand_sampling_edges.geom)
            )
            AND NOT EXISTS (
                SELECT 1
                FROM zones
                JOIN areas
                    ON areas.id = p_area_id
                    AND st_intersects(zones.geom, areas.geom)
                JOIN demand_sampling_edges
                    ON st_intersects(zones.geom, demand_sampling_edges.geom)
                WHERE st_intersects(zones.geom, selected_demand_in_area.destination_zone_geom)
            )
        ) AS zones_without_neighborhood_nodes;

        unmatched_request_ratio := CASE
            WHEN p_in_area_request_count = 0 THEN 0
            ELSE unmatched_request_count::numeric / p_in_area_request_count::numeric
        END;


        IF unmatched_request_ratio > unmatched_request_threshold_ratio THEN
            RAISE EXCEPTION 'Joining failed even for neighborhood zones. % in-area requests have no matching origin/destination nodes (% %% of % requests), above threshold 5%%. Zone ids: %.',
                unmatched_request_count,
                round(100 * unmatched_request_ratio, 2),
                p_in_area_request_count,
                missing_node_zones;
        END IF;

        IF unmatched_request_count > 0 THEN
            RAISE NOTICE '% in-area requests will be left without positions because no origin/destination nodes were found even in neighborhood zones (% %% of % requests). Threshold is 5%%. Zone ids: %.',
                unmatched_request_count,
                round(100 * unmatched_request_ratio, 2),
                p_in_area_request_count,
                missing_node_zones;
        END IF;
    END IF;

    RAISE NOTICE 'Sampling demand positions with neighborhood zones.';

    INSERT INTO trip_locations(request_id, origin, destination, set)
    SELECT
        sampled_nodes.request_id,
        sampled_nodes.origin,
        sampled_nodes.destination,
        p_trip_location_set_id AS set
    FROM (
        SELECT
            selected_demand_in_area.id AS request_id,
            coalesce(origin_nodes.node_id, origin_neighborhood_nodes.node_id) AS origin,
            coalesce(destination_nodes.node_id, destination_neighborhood_nodes.node_id) AS destination
        FROM selected_demand_in_area
        LEFT JOIN LATERAL (
            SELECT demand_sampling_edges."from" AS node_id
            FROM demand_sampling_edges
            WHERE st_intersects(selected_demand_in_area.origin_zone_geom, demand_sampling_edges.geom)
            ORDER BY random()
            LIMIT 1
        ) AS origin_nodes ON TRUE
        LEFT JOIN LATERAL (
            SELECT demand_sampling_edges."from" AS node_id
            FROM demand_sampling_edges
            WHERE st_intersects(selected_demand_in_area.destination_zone_geom, demand_sampling_edges.geom)
            ORDER BY random()
            LIMIT 1
        ) AS destination_nodes ON TRUE
        LEFT JOIN LATERAL (
            SELECT demand_sampling_edges."from" AS node_id
            FROM zones
            JOIN areas
                ON areas.id = p_area_id
                AND st_intersects(zones.geom, areas.geom)
            JOIN demand_sampling_edges
                ON st_intersects(zones.geom, demand_sampling_edges.geom)
            WHERE st_intersects(zones.geom, selected_demand_in_area.origin_zone_geom)
            ORDER BY random()
            LIMIT 1
        ) AS origin_neighborhood_nodes ON TRUE
        LEFT JOIN LATERAL (
            SELECT demand_sampling_edges."from" AS node_id
            FROM zones
            JOIN areas
                ON areas.id = p_area_id
                AND st_intersects(zones.geom, areas.geom)
            JOIN demand_sampling_edges
                ON st_intersects(zones.geom, demand_sampling_edges.geom)
            WHERE st_intersects(zones.geom, selected_demand_in_area.destination_zone_geom)
            ORDER BY random()
            LIMIT 1
        ) AS destination_neighborhood_nodes ON TRUE
    ) AS sampled_nodes
    WHERE sampled_nodes.origin IS NOT NULL
        AND sampled_nodes.destination IS NOT NULL;

    GET DIAGNOSTICS inserted_count = ROW_COUNT;

    IF inserted_count <> matched_request_count THEN
        RAISE EXCEPTION 'Inserted % neighborhood-sampled trip_locations rows, but % in-area requests had matching origin/destination nodes.',
            inserted_count, matched_request_count;
    END IF;

    RETURN inserted_count;
END;
$$;
