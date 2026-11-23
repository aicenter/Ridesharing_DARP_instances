------------------------------------------------------------------------------------------------------------------------
-- Calibrates one speed factor for an area: the multiplier of the edge speeds (Road Graph Tool
-- dm_generator.speed_factor) with which the travel times on the road network match the recorded trip durations
-- of the demand in total.
--
-- The demand is recorded between zones, so the travel time of a trip is the travel time between the representative
-- nodes of its origin and destination zones (select_zone_representative_nodes), computed with the speeds stored in
-- edges (posted speeds). The edge travel time is rounded to seconds as in the Road Graph Tool distance matrix
-- generator.
--
-- A trip is used if it has a recorded duration (destination_time), its zones differ and both have a representative
-- node, the duration is within [p_min_duration, p_max_duration], and the ratio of the duration to the network travel
-- time is within [p_min_ratio, p_max_ratio].
--
--      speed_factor = sum(network travel time) / sum(recorded duration) over the used trips
--
-- Parameters:
--      - p_area_id: the area, contracted with posted speeds (edges.speed filled).
--      - p_area_srid: projected SRID of the area, used for the edge lengths (metres).
--      - p_demand_dataset_ids, p_start_time, p_end_time, p_zone_types, p_ignored_zones: the demand selection, as
--          in generate_demand_positions.
--      - p_min_duration, p_max_duration: limits of the recorded trip duration.
--      - p_min_ratio, p_max_ratio: limits of the ratio recorded duration / network travel time.
-- Returns: one row with the speed factor, the counts of the selected trips by their use (trips_total is the sum of
--      the other trip counts), the number of zone pairs of the used trips, and the mean and median of the ratio
--      recorded duration / network travel time over the used trips.
-- Required tables: demand, zones, areas, nodes, edges, component_data, ways, nodes_ways, ways_tags, tags
-- Affected tables: None
------------------------------------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION compute_speed_factor(
    IN p_area_id smallint,
    IN p_area_srid integer,
    IN p_demand_dataset_ids integer[],
    IN p_start_time timestamp DEFAULT NULL,
    IN p_end_time timestamp DEFAULT NULL,
    IN p_zone_types smallint[] DEFAULT NULL,
    IN p_ignored_zones bigint[] DEFAULT NULL,
    IN p_min_duration interval DEFAULT '1 minute',
    IN p_max_duration interval DEFAULT '3 hours',
    IN p_min_ratio double precision DEFAULT 0.5,
    IN p_max_ratio double precision DEFAULT 10
)
RETURNS TABLE (
    speed_factor double precision,
    trips_total bigint,
    trips_used bigint,
    trips_without_duration bigint,
    trips_intra_zone bigint,
    trips_zone_without_nodes bigint,
    trips_filtered bigint,
    zone_pairs bigint,
    mean_ratio double precision,
    median_ratio double precision
)
LANGUAGE plpgsql
AS
$$
DECLARE
    v_min_duration double precision := extract(epoch FROM p_min_duration);
    v_max_duration double precision := extract(epoch FROM p_max_duration);
    v_zone_count bigint;
    v_representative_count bigint;
    v_outside_circle_count bigint;
    v_speed_factor double precision;
    v_trips_total bigint;
    v_trips_used bigint;
    v_trips_without_duration bigint;
    v_trips_intra_zone bigint;
    v_trips_zone_without_nodes bigint;
    v_trips_filtered bigint;
    v_zone_pairs bigint;
    v_mean_ratio double precision;
    v_median_ratio double precision;
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

    IF v_min_duration > v_max_duration THEN
        RAISE EXCEPTION 'p_min_duration (%) must not exceed p_max_duration (%).', p_min_duration, p_max_duration;
    END IF;

    IF p_min_ratio <= 0 OR p_min_ratio > p_max_ratio THEN
        RAISE EXCEPTION 'p_min_ratio (%) must be positive and must not exceed p_max_ratio (%).',
            p_min_ratio, p_max_ratio;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM edges WHERE edges.area = p_area_id) THEN
        RAISE EXCEPTION 'Area % has no edges. Contract the graph of the area first.', p_area_id;
    END IF;

    IF EXISTS (SELECT 1 FROM edges WHERE edges.area = p_area_id AND edges.speed IS NULL) THEN
        RAISE EXCEPTION 'Some edges of area % have no speed. Contract the graph with contraction.speed_source: posted.',
            p_area_id;
    END IF;

    CALL create_demand_sampling_edges(p_area_id);

    CALL create_selected_demand(p_demand_dataset_ids, p_start_time, p_end_time, p_ignored_zones);

    PERFORM validate_selected_demand_zones(p_zone_types);

    CALL create_zones_in_area(p_area_id, p_zone_types);

    -- representative nodes of the zones
    DROP TABLE IF EXISTS speed_factor_zone_nodes;
    CREATE TEMPORARY TABLE speed_factor_zone_nodes ON COMMIT DROP AS
    SELECT
        representative_nodes.zone_id,
        representative_nodes.node_id,
        representative_nodes.in_circle
    FROM select_zone_representative_nodes(p_area_id, p_area_srid) AS representative_nodes;

    CREATE INDEX speed_factor_zone_nodes_zone_id_idx ON speed_factor_zone_nodes(zone_id);
    ANALYZE speed_factor_zone_nodes;

    SELECT count(1) INTO v_zone_count FROM zones_in_area;
    SELECT count(1), count(1) FILTER (WHERE NOT speed_factor_zone_nodes.in_circle)
    INTO v_representative_count, v_outside_circle_count
    FROM speed_factor_zone_nodes;
    RAISE NOTICE '% of % zones have a representative node, % of them outside the circle around the zone centroid.',
        v_representative_count, v_zone_count, v_outside_circle_count;

    -- the selected trips with both zones in the area, by their use. The trips are joined to the zones directly:
    -- create_selected_demand_in_area copies both zone geometries to each trip, which takes too much space for the
    -- number of trips used here.
    DROP TABLE IF EXISTS speed_factor_trips;
    CREATE TEMPORARY TABLE speed_factor_trips ON COMMIT DROP AS
    SELECT
        origin_nodes.node_id AS origin_node,
        destination_nodes.node_id AS destination_node,
        extract(epoch FROM selected_demand.destination_time - selected_demand.origin_time)
            ::double precision AS duration,
        CASE
            WHEN selected_demand.destination_time IS NULL THEN 'without_duration'
            WHEN selected_demand.origin = selected_demand.destination THEN 'intra_zone'
            WHEN origin_nodes.node_id IS NULL OR destination_nodes.node_id IS NULL THEN 'zone_without_nodes'
            ELSE 'candidate'
        END AS category
    FROM selected_demand
    JOIN zones_in_area AS origin_zones
        ON origin_zones.id = selected_demand.origin
    JOIN zones_in_area AS destination_zones
        ON destination_zones.id = selected_demand.destination
    LEFT JOIN speed_factor_zone_nodes AS origin_nodes
        ON origin_nodes.zone_id = origin_zones.id
    LEFT JOIN speed_factor_zone_nodes AS destination_nodes
        ON destination_nodes.zone_id = destination_zones.id;

    ANALYZE speed_factor_trips;

    SELECT
        count(1),
        count(1) FILTER (WHERE speed_factor_trips.category = 'without_duration'),
        count(1) FILTER (WHERE speed_factor_trips.category = 'intra_zone'),
        count(1) FILTER (WHERE speed_factor_trips.category = 'zone_without_nodes')
    INTO v_trips_total, v_trips_without_duration, v_trips_intra_zone, v_trips_zone_without_nodes
    FROM speed_factor_trips;

    IF v_trips_total = v_trips_without_duration THEN
        RAISE EXCEPTION 'None of the % selected trips has a recorded duration (destination_time).', v_trips_total;
    END IF;

    -- network travel times between the representative nodes of the zone pairs of the trips
    DROP TABLE IF EXISTS speed_factor_node_pairs;
    CREATE TEMPORARY TABLE speed_factor_node_pairs ON COMMIT DROP AS
    SELECT DISTINCT
        speed_factor_trips.origin_node AS source,
        speed_factor_trips.destination_node AS target
    FROM speed_factor_trips
    WHERE speed_factor_trips.category = 'candidate'
        AND speed_factor_trips.origin_node != speed_factor_trips.destination_node;

    RAISE NOTICE 'Computing network travel times for % zone pairs.', (SELECT count(1) FROM speed_factor_node_pairs);

    DROP TABLE IF EXISTS speed_factor_travel_times;
    CREATE TEMPORARY TABLE speed_factor_travel_times ON COMMIT DROP AS
    SELECT
        costs.start_vid AS source,
        costs.end_vid AS target,
        costs.agg_cost AS travel_time
    FROM pgr_dijkstraCost(
        format(
            'SELECT id, "from" AS source, "to" AS target,'
            ' round(st_length(st_transform(geom, %s)) / speed * 3.6)::double precision AS cost'
            ' FROM edges WHERE area = %s',
            p_area_srid,
            p_area_id
        ),
        'SELECT source, target FROM speed_factor_node_pairs',
        directed => true
    ) AS costs;

    CREATE INDEX speed_factor_travel_times_idx ON speed_factor_travel_times(source, target);
    ANALYZE speed_factor_travel_times;

    -- the used trips and the factor
    SELECT
        count(1),
        sum(used_trips.travel_time) / sum(used_trips.duration),
        count(DISTINCT (used_trips.origin_node, used_trips.destination_node)),
        avg(used_trips.duration / used_trips.travel_time),
        percentile_cont(0.5) WITHIN GROUP (ORDER BY used_trips.duration / used_trips.travel_time)
    INTO v_trips_used, v_speed_factor, v_zone_pairs, v_mean_ratio, v_median_ratio
    FROM (
        SELECT
            speed_factor_trips.origin_node,
            speed_factor_trips.destination_node,
            speed_factor_trips.duration,
            speed_factor_travel_times.travel_time
        FROM speed_factor_trips
        JOIN speed_factor_travel_times
            ON speed_factor_travel_times.source = speed_factor_trips.origin_node
            AND speed_factor_travel_times.target = speed_factor_trips.destination_node
        WHERE speed_factor_trips.category = 'candidate'
            AND speed_factor_travel_times.travel_time > 0
            AND speed_factor_trips.duration BETWEEN v_min_duration AND v_max_duration
            AND speed_factor_trips.duration / speed_factor_travel_times.travel_time
                BETWEEN p_min_ratio AND p_max_ratio
    ) AS used_trips;

    v_trips_filtered := v_trips_total - v_trips_without_duration - v_trips_intra_zone - v_trips_zone_without_nodes
        - v_trips_used;

    IF v_trips_used = 0 THEN
        RAISE EXCEPTION 'No trip can be used for the speed factor (% selected, % without duration, % within one zone, % with a zone without nodes, % filtered).',
            v_trips_total, v_trips_without_duration, v_trips_intra_zone, v_trips_zone_without_nodes,
            v_trips_filtered;
    END IF;

    RAISE NOTICE 'Speed factor % computed from % of % selected trips.', v_speed_factor, v_trips_used, v_trips_total;

    DROP TABLE IF EXISTS speed_factor_travel_times;
    DROP TABLE IF EXISTS speed_factor_node_pairs;
    DROP TABLE IF EXISTS speed_factor_trips;
    DROP TABLE IF EXISTS speed_factor_zone_nodes;
    DROP TABLE IF EXISTS selected_demand;
    DROP TABLE IF EXISTS zones_in_area;
    DROP TABLE IF EXISTS demand_sampling_edges;

    RETURN QUERY
    SELECT
        v_speed_factor,
        v_trips_total,
        v_trips_used,
        v_trips_without_duration,
        v_trips_intra_zone,
        v_trips_zone_without_nodes,
        v_trips_filtered,
        v_zone_pairs,
        v_mean_ratio,
        v_median_ratio;
END;
$$;
