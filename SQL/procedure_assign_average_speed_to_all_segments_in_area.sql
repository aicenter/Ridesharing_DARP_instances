CREATE OR REPLACE PROCEDURE assign_average_speed_to_all_segments_in_area(
	IN target_area_id smallint,
	IN target_area_srid integer
)
LANGUAGE plpgsql
AS $$
DECLARE
    row_count integer;
BEGIN

RAISE NOTICE 'assigning average speed to all segments in area %', (SELECT name FROM areas WHERE id = target_area_id);
WITH average_speed AS (
	SELECT
		AVG(speed) AS average_speed,
		AVG(st_dev) AS average_st_dev,
		count(1) AS count
		FROM nodes_ways_speeds
		WHERE quality IN (1, 2)
),
target_ways AS (
    SELECT * FROM get_ways_in_target_area(target_area_id::smallint)
),
node_segments AS (
	SELECT
		from_nodes_ways.id AS from_id,
		to_node_ways.id AS to_id,
		st_transform(st_makeline(from_nodes.geom, to_nodes.geom), target_area_srid::integer) AS geom
	FROM
		nodes_ways from_nodes_ways
			JOIN target_ways ON from_nodes_ways.way_id = target_ways.id
			JOIN nodes_ways to_node_ways
				 ON from_nodes_ways.way_id = to_node_ways.way_id
				 AND (
						from_nodes_ways.position = to_node_ways.position - 1
						OR (from_nodes_ways.position = to_node_ways.position + 1 AND target_ways.oneway = false)
					)
			JOIN nodes from_nodes ON from_nodes_ways.node_id = from_nodes.id
			JOIN nodes to_nodes ON to_node_ways.node_id = to_nodes.id
)
INSERT INTO nodes_ways_speeds
SELECT
	from_id, average_speed, average_st_dev, to_id, 5 AS quality, count
FROM node_segments
	JOIN average_speed ON TRUE
ON CONFLICT DO NOTHING; -- handle overlapping areas

GET DIAGNOSTICS row_count = ROW_COUNT;
RAISE NOTICE 'Average speed assigned to % segments', row_count;
END;
$$