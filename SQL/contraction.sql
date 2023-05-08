
-- -- road segments table
-- DROP TABLE IF EXISTS road_segments;
-- CREATE TEMPORARY TABLE road_segments AS (
-- 	SELECT * FROM select_node_segments_in_area(12::smallint, 32618)
-- );
-- CREATE INDEX road_segments_index_from_to ON road_segments (from_id, to_id);

-- DROP TABLE IF EXISTS contractions;
-- CREATE TEMPORARY TABLE contractions AS (
-- 	SELECT
-- 	    id,
-- 		source,
-- 		target,
-- 		unnest(contracted_vertices) AS contracted_vertex
-- 		FROM
-- 			pgr_contraction(
-- 					'SELECT row_number() OVER () AS id, "from_node" AS source, "to_node" AS target, 0 AS cost FROM road_segments',
-- 					ARRAY [2]
-- 				)
-- );
-- CREATE INDEX contractions_index_contracted_vertex ON contractions (contracted_vertex);
-- CREATE INDEX contractions_index_from_to ON contractions (source, target);
--
-- UPDATE nodes
-- 	SET contracted = TRUE
-- WHERE id IN (
-- 	SELECT contracted_vertex
-- 	FROM contractions
-- );


-- edges for non contracted road segments
-- INSERT INTO edges ("from", "to", geom, area)
-- SELECT
-- 	road_segments.from_node,
-- 	road_segments.to_node,
-- 	st_multi(st_makeline(from_nodes.geom, to_nodes.geom)) as geom,
-- 	12 AS area,
-- 	speed
-- 	FROM road_segments
-- 		JOIN nodes from_nodes ON from_nodes.id  = from_node AND from_nodes.contracted = FALSE
-- 		JOIN nodes to_nodes ON to_nodes.id  = to_node AND to_nodes.contracted = FALSE
-- 	JOIN ways ON ways.id = road_segments.way_id


-- contraction segments generation
-- DROP TABLE IF EXISTS contraction_segments;
-- CREATE TEMPORARY TABLE contraction_segments AS (
-- SELECT
--     from_contraction.id,
-- 	from_contraction.contracted_vertex AS from_node,
-- 	to_contraction.contracted_vertex AS to_node,
-- 	geom,
-- 	speed
-- FROM
--     contractions from_contraction
-- 	JOIN contractions to_contraction
-- 	    ON from_contraction.id = to_contraction.id
-- 	JOIN road_segments
-- 	    ON road_segments.from_node = from_contraction.contracted_vertex
-- 		AND road_segments.to_node = to_contraction.contracted_vertex
-- UNION
-- SELECT
--     id,
--     source AS from_node,
--     contracted_vertex AS to_node,
-- 	geom,
-- 	speed
-- FROM contractions
-- 	JOIN road_segments ON road_segments.from_node = source AND road_segments.to_node = contracted_vertex
-- UNION
-- SELECT
--     id,
--     contracted_vertex AS from_node,
--     target AS to_node,
-- 	geom,
-- 	speed
-- FROM contractions
-- 	JOIN road_segments ON road_segments.from_node = contracted_vertex AND road_segments.to_node = target
-- );

-- edges for contracted road segments
INSERT INTO edges ("from", "to", area, geom, speed)
SELECT
	max(source) AS "from",
	max(target) AS "to",
	12 AS area,
	st_transform(st_union(geom), 4326) AS geom,
	sum(speed * st_length(geom)) / sum(st_length(geom)) AS speed
	FROM contractions
	    JOIN contraction_segments ON contraction_segments.id = contractions.id
	GROUP BY contractions.id



-- SELECT * FROM contraction_segments WHERE id = -108288;


-- check how many segments are contracted
-- SELECT COUNT(DISTINCT road_segments.id)
-- FROM road_segments
-- JOIN nodes ON nodes.id IN ("from", "to") AND contracted = TRUE
-- SELECT count(1) FROM contraction_segments;

-- SELECT * FROM contractions
-- ORDER BY id ASC

-- SELECT
--     DISTINCT id,
--     first_value(position) OVER w AS max_position
-- FROM contractions
-- WINDOW w AS (PARTITION BY id ORDER BY position DESC)
-- ORDER BY id ASC


