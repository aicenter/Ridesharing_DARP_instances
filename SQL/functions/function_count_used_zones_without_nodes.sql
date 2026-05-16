CREATE OR REPLACE FUNCTION count_used_zones_without_nodes()
RETURNS integer
LANGUAGE plpgsql
AS
$$
DECLARE
    missing_node_zones bigint[];
    missing_count integer;
    zone_count integer;
    missing_ratio numeric;
    missing_threshold_ratio numeric := 0.10;
BEGIN
    RAISE NOTICE 'Counting used zones without nodes';

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
        UNION
        SELECT DISTINCT destination_zone_id AS zone_id
        FROM selected_demand_in_area
        WHERE NOT EXISTS (
            SELECT 1
            FROM demand_sampling_edges
            WHERE st_intersects(selected_demand_in_area.destination_zone_geom, demand_sampling_edges.geom)
        )
    ) AS zones_without_nodes;

    missing_count := coalesce(cardinality(missing_node_zones), 0);

    SELECT count(1) INTO zone_count FROM zones_in_area;

    missing_ratio := CASE
        WHEN zone_count = 0 THEN 0
        ELSE missing_count::numeric / zone_count::numeric
    END;

    IF missing_ratio > missing_threshold_ratio THEN
        RAISE EXCEPTION 'Joining zones to nodes failed. % zones have no matching demand_sampling_edges (% %% of % zones_in_area rows), above threshold 10%%. Zone ids: %.',
            missing_count, round(100 * missing_ratio, 2), zone_count, missing_node_zones;
    END IF;

    IF missing_count > 0 THEN
        RAISE NOTICE '% used zones have no matching demand_sampling_edges (% %% of % zones in area). Threshold is 10%%.',
            missing_count, round(100 * missing_ratio, 2), zone_count;
    END IF;

    RETURN missing_count;
END;
$$;
