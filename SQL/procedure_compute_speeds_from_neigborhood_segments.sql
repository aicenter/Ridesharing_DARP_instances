CREATE OR REPLACE PROCEDURE compute_speeds_from_neighborhood_segments(
	IN target_area_id smallint,
	IN target_area_srid integer
)
LANGUAGE plpgsql
AS $$
DECLARE
    assigned_segments_count INTEGER;
	new_assigned_segments_count INTEGER;
BEGIN

RAISE NOTICE 'selecting target ways';
EXECUTE format('
CREATE MATERIALIZED VIEW target_ways AS
(
	SELECT ways.* FROM ways JOIN areas ON areas.id = %L AND st_intersects(areas.geom, ways.geom)
)', target_area_id);
CREATE INDEX target_ways_id_idx ON target_ways(id);
RAISE NOTICE '% ways selected', (SELECT count(1) FROM target_ways);

RAISE NOTICE 'creating node segments view';
EXECUTE format('
CREATE MATERIALIZED VIEW node_segments AS
(
	SELECT
		from_nodes_ways.id AS from_id,
		to_node_ways.id AS to_id,
		st_transform(st_makeline(from_nodes.geom, to_nodes.geom), %L::integer) AS geom
	FROM
		nodes_ways from_nodes_ways
	JOIN target_ways ON from_nodes_ways.way_id = target_ways.id
	JOIN nodes_ways to_node_ways
		 ON from_nodes_ways.way_id = to_node_ways.way_id
			 AND (
					from_nodes_ways.position = to_node_ways.position - 1
					OR (from_nodes_ways.position = to_node_ways.position + 1 AND target_ways.oneway = false)
				)
	LEFT JOIN nodes_ways_speeds ON
			from_nodes_ways.id = nodes_ways_speeds.from_node_ways_id
		AND to_node_ways.id = nodes_ways_speeds.to_node_ways_id
	JOIN nodes from_nodes ON from_nodes_ways.node_id = from_nodes.id
	JOIN nodes to_nodes ON to_node_ways.node_id = to_nodes.id
	WHERE nodes_ways_speeds.to_node_ways_id IS NULL
)', target_area_srid);
CREATE INDEX node_segments_osm_id_idx ON node_segments(from_id, to_id);
CREATE INDEX node_segments_geom_idx
	ON node_segments
		USING GIST (geom);
RAISE NOTICE '% node segments without assign speeds found in target area', (SELECT count(1) FROM node_segments);

RAISE NOTICE 'joining speeds computed using speed records to segments';
CREATE TEMPORARY TABLE speed_segment_data AS
SELECT
	st_transform(st_makeline(from_nodes.geom, to_nodes.geom), target_area_srid) AS geom,
	speed,
	st_dev
FROM nodes_ways_speeds
    JOIN nodes_ways from_nodes_ways ON
        nodes_ways_speeds.quality <= 2
        AND nodes_ways_speeds.from_node_ways_id = from_nodes_ways.id
	JOIN nodes_ways to_node_ways ON to_node_ways_id = to_node_ways.id
	JOIN target_ways ON from_nodes_ways.way_id = target_ways.id AND to_node_ways.way_id = target_ways.id
	JOIN nodes from_nodes ON from_nodes_ways.node_id = from_nodes.id
	JOIN nodes to_nodes ON to_node_ways.node_id = to_nodes.id;
CREATE INDEX speed_segment_data_geom_idx
	ON speed_segment_data
	USING GIST (geom);
assigned_segments_count = (SELECT count(1) FROM speed_segment_data);
RAISE NOTICE '% segments with assigned speed  found in target area', assigned_segments_count;

CREATE VIEW assigned_segments_in_target_area AS
	SELECT count(1)
		FROM nodes_ways_speeds
				 JOIN nodes_ways from_nodes_ways ON nodes_ways_speeds.from_node_ways_id = from_nodes_ways.id
				 JOIN nodes_ways to_node_ways ON to_node_ways_id = to_node_ways.id
				 JOIN target_ways ON from_nodes_ways.way_id = target_ways.id AND to_node_ways.way_id = target_ways.id;

RAISE NOTICE 'computing speed for segments using speed segments within 10 m distance';
INSERT INTO nodes_ways_speeds
SELECT
    from_id, speed, st_dev, to_id, 3 AS quality, count
FROM node_segments
 JOIN LATERAL (
	SELECT
	    avg(speed) AS speed,
		avg(st_dev) AS st_dev,
		count(1) AS count
	FROM speed_segment_data
	WHERE st_intersects(st_buffer(node_segments.geom, 10), speed_segment_data.geom)
) computed_speed_small_neighborhood ON TRUE
WHERE speed IS NOT NULL;
new_assigned_segments_count = (SELECT count FROM assigned_segments_in_target_area);
RAISE NOTICE 'speed from close neighborhood computed for % segments', new_assigned_segments_count - assigned_segments_count;
assigned_segments_count = new_assigned_segments_count;

RAISE NOTICE 'computing speed for segments using speed segments within 200 m distance';
REFRESH MATERIALIZED VIEW node_segments;
INSERT INTO nodes_ways_speeds
SELECT
	from_id, speed, st_dev, to_id, 4 AS quality, count
	FROM node_segments
			 JOIN LATERAL (
			SELECT
				avg(speed) AS speed,
				avg(st_dev) AS st_dev,
				count(1) AS count
				FROM speed_segment_data
				WHERE st_intersects(st_buffer(node_segments.geom, 200), speed_segment_data.geom)
			) computed_speed_small_neighborhood ON TRUE
	WHERE speed IS NOT NULL;
new_assigned_segments_count = (SELECT count FROM assigned_segments_in_target_area);
RAISE NOTICE 'speed from distant neighborhood computed for % segments', new_assigned_segments_count - assigned_segments_count;
assigned_segments_count = new_assigned_segments_count;

RAISE NOTICE 'computing speed for remaining segments using average speed';
REFRESH MATERIALIZED VIEW node_segments;
WITH average_speed AS (
	SELECT
	    AVG(speed) AS average_speed,
		AVG(st_dev) AS average_st_dev,
		count(1) AS count
	FROM speed_segment_data
)
INSERT INTO nodes_ways_speeds
SELECT
	from_id, average_speed, average_st_dev, to_id, 5 AS quality, count
	FROM node_segments
	JOIN average_speed ON TRUE;
new_assigned_segments_count = (SELECT count FROM assigned_segments_in_target_area);
RAISE NOTICE 'Average speed assigned to % segments', new_assigned_segments_count - assigned_segments_count;


DROP TABLE IF EXISTS speed_segment_data;
DROP MATERIALIZED VIEW IF EXISTS node_segments;
DROP VIEW IF EXISTS assigned_segments_in_target_area;
DROP MATERIALIZED VIEW IF EXISTS target_ways;
END
$$

