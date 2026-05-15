CREATE OR REPLACE PROCEDURE create_demand_sampling_edges(IN p_area_id smallint)
LANGUAGE plpgsql
AS
$$
DECLARE
    edge_count bigint;
BEGIN
    DROP TABLE IF EXISTS demand_sampling_edges;

    RAISE NOTICE 'Creating demand sampling edges table for area %', p_area_id;

    CREATE TEMPORARY TABLE demand_sampling_edges ON COMMIT DROP AS
    SELECT DISTINCT
        edges."from",
        edges.geom
    FROM edges
    JOIN select_network_nodes_in_area(p_area_id) AS from_nodes
        ON edges.area = p_area_id
        AND edges."from" = from_nodes.id
    JOIN nodes_ways AS from_node_ways
        ON from_nodes.id = from_node_ways.node_id
    JOIN ways
        ON from_node_ways.way_id = ways.id
    WHERE ways.tags->'highway' NOT IN ('motorway', 'motorway_link', 'trunk', 'trunk_link');

    SELECT count(1) INTO edge_count FROM demand_sampling_edges;
    IF edge_count = 0 THEN
        RAISE EXCEPTION 'No demand sampling edges found for area %', p_area_id;
    END IF;
    RAISE NOTICE 'Created % demand sampling edges. Generating geometry index.', edge_count;

    CREATE INDEX demand_sampling_edges_geom_idx ON demand_sampling_edges USING GIST(geom);
END;
$$;
