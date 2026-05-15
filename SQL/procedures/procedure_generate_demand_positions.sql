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
    v_trip_count bigint;
    v_outside_zone_count bigint;
    v_outside_request_count bigint;
    v_in_area_trip_count bigint;
    v_existing_location_count bigint;
    v_missing_zone_ids bigint[];
    v_ambiguous_zone_ids bigint[];
    v_missing_node_zones bigint[];
    v_missing_count integer;
    v_missing_threshold integer := 10;
    v_with_nodes_count bigint;
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

    DROP TABLE IF EXISTS pg_temp.selected_demand;
    CREATE TEMPORARY TABLE selected_demand ON COMMIT DROP AS
    SELECT demand.*
    FROM demand
    WHERE dataset = ANY(p_demand_dataset_ids)
        AND (p_start_time IS NULL OR origin_time >= p_start_time)
        AND (p_end_time IS NULL OR origin_time <= p_end_time)
        AND (
            p_ignored_zones IS NULL
            OR cardinality(p_ignored_zones) = 0
            OR (
                origin <> ALL(p_ignored_zones)
                AND destination <> ALL(p_ignored_zones)
            )
        );
    CREATE INDEX selected_demand_id_idx ON selected_demand(id);
    CREATE INDEX selected_demand_origin_idx ON selected_demand(origin);
    CREATE INDEX selected_demand_destination_idx ON selected_demand(destination);
    ANALYZE selected_demand;

    SELECT count(1) INTO v_trip_count FROM selected_demand;
    RAISE NOTICE 'Selected % demand requests before area filtering.', v_trip_count;

    SELECT array_agg(zone_id ORDER BY zone_id)
    INTO v_missing_zone_ids
    FROM (
        SELECT DISTINCT origin AS zone_id
        FROM selected_demand
        WHERE NOT EXISTS (
            SELECT 1
            FROM zones AS oz
            WHERE oz.id = selected_demand.origin
                AND (
                    p_zone_types IS NULL
                    OR cardinality(p_zone_types) = 0
                    OR oz.type = ANY(p_zone_types)
                )
        )
        UNION
        SELECT DISTINCT destination AS zone_id
        FROM selected_demand
        WHERE NOT EXISTS (
            SELECT 1
            FROM zones AS dz
            WHERE dz.id = selected_demand.destination
                AND (
                    p_zone_types IS NULL
                    OR cardinality(p_zone_types) = 0
                    OR dz.type = ANY(p_zone_types)
                )
        )
    ) AS missing_zones;

    IF v_missing_zone_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Some demand origin/destination zone ids have no matching zones for the requested zone types: %.',
            v_missing_zone_ids;
    END IF;

    SELECT array_agg(zone_id ORDER BY zone_id)
    INTO v_ambiguous_zone_ids
    FROM (
        SELECT used_zones.zone_id
        FROM (
            SELECT DISTINCT origin AS zone_id FROM selected_demand
            UNION
            SELECT DISTINCT destination AS zone_id FROM selected_demand
        ) AS used_zones
        JOIN zones
            ON zones.id = used_zones.zone_id
            AND (
                p_zone_types IS NULL
                OR cardinality(p_zone_types) = 0
                OR zones.type = ANY(p_zone_types)
            )
        GROUP BY used_zones.zone_id
        HAVING count(1) > 1
    ) AS ambiguous_zones;

    IF v_ambiguous_zone_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Some demand zone ids match more than one zone. Pass a narrower p_zone_types array. Ambiguous zone ids: %.',
            v_ambiguous_zone_ids;
    END IF;

    SELECT count(DISTINCT zone_id), count(DISTINCT request_id)
    INTO v_outside_zone_count, v_outside_request_count
    FROM (
        SELECT oz.id AS zone_id, selected_demand.id AS request_id
        FROM selected_demand
        JOIN zones AS oz
            ON selected_demand.origin = oz.id
            AND (
                p_zone_types IS NULL
                OR cardinality(p_zone_types) = 0
                OR oz.type = ANY(p_zone_types)
            )
        LEFT JOIN areas AS origin_areas
            ON origin_areas.id = p_area_id
            AND st_intersects(origin_areas.geom, oz.geom)
        WHERE origin_areas.id IS NULL
        UNION
        SELECT dz.id AS zone_id, selected_demand.id AS request_id
        FROM selected_demand
        JOIN zones AS dz
            ON selected_demand.destination = dz.id
            AND (
                p_zone_types IS NULL
                OR cardinality(p_zone_types) = 0
                OR dz.type = ANY(p_zone_types)
            )
        LEFT JOIN areas AS destination_areas
            ON destination_areas.id = p_area_id
            AND st_intersects(destination_areas.geom, dz.geom)
        WHERE destination_areas.id IS NULL
    ) AS outside_area;

    IF v_outside_zone_count > 0 THEN
        RAISE NOTICE '% zones will be ignored because they are outside the selected area.', v_outside_zone_count;
        RAISE NOTICE '% requests will be ignored because they are outside the selected area.', v_outside_request_count;
    END IF;

    DROP TABLE IF EXISTS pg_temp.selected_demand_in_area;
    CREATE TEMPORARY TABLE selected_demand_in_area ON COMMIT DROP AS
    SELECT
        selected_demand.*,
        oz.id AS origin_zone_id,
        oz.geom AS origin_zone_geom,
        dz.id AS destination_zone_id,
        dz.geom AS destination_zone_geom
    FROM selected_demand
    JOIN zones AS oz
        ON selected_demand.origin = oz.id
        AND (
            p_zone_types IS NULL
            OR cardinality(p_zone_types) = 0
            OR oz.type = ANY(p_zone_types)
        )
    JOIN areas AS origin_areas
        ON origin_areas.id = p_area_id
        AND st_intersects(origin_areas.geom, oz.geom)
    JOIN zones AS dz
        ON selected_demand.destination = dz.id
        AND (
            p_zone_types IS NULL
            OR cardinality(p_zone_types) = 0
            OR dz.type = ANY(p_zone_types)
        )
    JOIN areas AS destination_areas
        ON destination_areas.id = p_area_id
        AND st_intersects(destination_areas.geom, dz.geom);
    CREATE INDEX selected_demand_in_area_id_idx ON selected_demand_in_area(id);
    ANALYZE selected_demand_in_area;

    SELECT count(1) INTO v_in_area_trip_count FROM selected_demand_in_area;
    RAISE NOTICE 'Selected % demand requests after area filtering.', v_in_area_trip_count;

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

    SELECT array_agg(zone_id ORDER BY zone_id)
    INTO v_missing_node_zones
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

    v_missing_count := coalesce(cardinality(v_missing_node_zones), 0);

    IF v_missing_count > v_missing_threshold THEN
        RAISE EXCEPTION 'Joining zones to nodes failed. % zones have no matching demand_sampling_edges, above threshold %. Zone ids: %.',
            v_missing_count, v_missing_threshold, v_missing_node_zones;
    END IF;

    IF v_missing_count > 0 THEN
        RAISE NOTICE '% used zones have no matching demand_sampling_edges. Searching neighborhood zones.', v_missing_count;

        SELECT count(1)
        INTO v_with_nodes_count
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

        IF v_with_nodes_count <> v_in_area_trip_count THEN
            SELECT array_agg(zone_id ORDER BY zone_id)
            INTO v_missing_node_zones
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

            RAISE EXCEPTION 'Joining failed even for neighborhood zones. % in-area requests have no matching origin/destination nodes. Zone ids: %.',
                v_in_area_trip_count - v_with_nodes_count, v_missing_node_zones;
        END IF;

        INSERT INTO trip_locations(request_id, origin, destination, set)
        SELECT
            selected_demand_in_area.id,
            coalesce(origin_nodes.node_id, origin_neighborhood_nodes.node_id) AS origin,
            coalesce(destination_nodes.node_id, destination_neighborhood_nodes.node_id) AS destination,
            v_trip_location_set_id AS set
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
        ) AS destination_neighborhood_nodes ON TRUE;
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
    END IF;

    GET DIAGNOSTICS v_inserted_count = ROW_COUNT;

    IF v_inserted_count <> v_in_area_trip_count THEN
        RAISE EXCEPTION 'Inserted % trip_locations rows, but % in-area demand requests were selected.',
            v_inserted_count, v_in_area_trip_count;
    END IF;

    RAISE NOTICE 'Inserted % trip_locations rows for trip_location_sets.id=%.', v_inserted_count, v_trip_location_set_id;

    DROP TABLE IF EXISTS pg_temp.selected_demand_in_area;
    DROP TABLE IF EXISTS pg_temp.selected_demand;
    DROP TABLE IF EXISTS pg_temp.demand_sampling_edges;
END;
$$;
