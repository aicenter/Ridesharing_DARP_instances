CREATE OR REPLACE PROCEDURE contract_graph_in_area(IN target_area_id smallint, IN target_area_srid integer)
LANGUAGE plpgsql
AS $$
DECLARE
    non_contracted_edges_count integer;
BEGIN
-- road segments table
RAISE NOTICE 'Creating road segments table';
CREATE TEMPORARY TABLE road_segments AS (
	SELECT * FROM select_node_segments_in_area(target_area_id, target_area_srid)
);
CREATE INDEX road_segments_index_from_to ON road_segments (from_id, to_id);
RAISE NOTICE 'Road segments table created: % road segments', (SELECT count(*) FROM road_segments);

RAISE NOTICE 'Contracting graph';
CREATE TEMPORARY TABLE contractions AS (
	SELECT
	    id,
		source,
		target,
		unnest(contracted_vertices) AS contracted_vertex
		FROM
			pgr_contraction(
				'SELECT row_number() OVER () AS id, "from_node" AS source, "to_node" AS target, 0 AS cost FROM road_segments',
				ARRAY [2]
			)
);
CREATE INDEX contractions_index_contracted_vertex ON contractions (contracted_vertex);
CREATE INDEX contractions_index_from_to ON contractions (source, target);
RAISE NOTICE '% nodes contracted', (SELECT count(*) FROM contractions);

-- update nodes
RAISE NOTICE 'Updating nodes';
UPDATE nodes
	SET contracted = TRUE
WHERE id IN (
	SELECT contracted_vertex
	FROM contractions
);

-- edges for non contracted road segments
RAISE NOTICE 'Creating edges for non-contracted road segments';
INSERT INTO edges ("from", "to", geom, area, speed)
SELECT
	road_segments.from_node,
	road_segments.to_node,
	st_multi(st_makeline(from_nodes.geom, to_nodes.geom)) as geom,
	target_area_id AS area,
	speed
	FROM road_segments
		JOIN nodes from_nodes ON from_nodes.id  = from_node AND from_nodes.contracted = FALSE
		JOIN nodes to_nodes ON to_nodes.id  = to_node AND to_nodes.contracted = FALSE
	JOIN ways ON ways.id = road_segments.way_id;
non_contracted_edges_count := (SELECT count(*) FROM edges WHERE area = target_area_id);
RAISE NOTICE '% Edges for non-contracted road segments created', non_contracted_edges_count;

-- contraction segments generation
RAISE NOTICE 'Generating contraction segments';
CREATE TEMPORARY TABLE contraction_segments AS (
SELECT
    from_contraction.id,
	from_contraction.contracted_vertex AS from_node,
	to_contraction.contracted_vertex AS to_node,
	geom,
	speed
FROM
    contractions from_contraction
	JOIN contractions to_contraction
	    ON from_contraction.id = to_contraction.id
	JOIN road_segments
	    ON road_segments.from_node = from_contraction.contracted_vertex
		AND road_segments.to_node = to_contraction.contracted_vertex
UNION
SELECT
    id,
    source AS from_node,
    contracted_vertex AS to_node,
	geom,
	speed
FROM contractions
	JOIN road_segments ON road_segments.from_node = source AND road_segments.to_node = contracted_vertex
UNION
SELECT
    id,
    contracted_vertex AS from_node,
    target AS to_node,
	geom,
	speed
FROM contractions
	JOIN road_segments ON road_segments.from_node = contracted_vertex AND road_segments.to_node = target
);
RAISE NOTICE '% contraction segments generated', (SELECT count(*) FROM contraction_segments);

-- edges for contracted road segments
RAISE NOTICE 'Creating edges for contracted road segments';
INSERT INTO edges ("from", "to", area, geom, speed)
SELECT
	max(source) AS "from",
	max(target) AS "to",
	target_area_id AS area,
	st_transform(st_multi(st_union(geom)), 4326) AS geom,
	sum(speed * st_length(geom)) / sum(st_length(geom)) AS speed
	FROM contractions
	    JOIN contraction_segments ON contraction_segments.id = contractions.id
	GROUP BY contractions.id;
RAISE NOTICE '% Edges for contracted road segments created', (SELECT count(*) FROM edges WHERE area = target_area_id) - non_contracted_edges_count;

DISCARD TEMPORARY;
END
$$