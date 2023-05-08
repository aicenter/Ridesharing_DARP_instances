CREATE OR REPLACE FUNCTION select_node_segments_in_area(IN target_area_id smallint, IN target_area_srid integer)
RETURNS TABLE
(
	from_id   integer,
	to_id     integer,
	from_node bigint,
	to_node   bigint,
	from_position smallint,
	to_position smallint,
	way_id    integer,
	geom      geometry,
	speed     float,
	quality   smallint
)
LANGUAGE plpgsql
AS $$
BEGIN
CREATE TEMPORARY TABLE target_ways AS
	SELECT * FROM get_ways_in_target_area(target_area_id);
CREATE INDEX target_ways_id_idx ON target_ways(id);
CREATE INDEX target_ways_oneway_idx ON target_ways(oneway);

RETURN QUERY
SELECT
	from_nodes_ways.id AS from_id,
	to_node_ways.id AS to_id,
	from_nodes.id AS from_node,
	to_nodes.id AS to_node,
	from_nodes_ways.position AS from_position,
	to_node_ways.position AS to_position,
	to_node_ways.way_id AS way_id,
	st_transform(st_makeline(from_nodes.geom, to_nodes.geom), target_area_srid) AS geom,
	nodes_ways_speeds.speed AS speed,
	nodes_ways_speeds.quality AS quality
	FROM
		nodes_ways from_nodes_ways
			JOIN target_ways ON from_nodes_ways.way_id = target_ways.id
			JOIN nodes_ways to_node_ways
				 ON from_nodes_ways.way_id = to_node_ways.way_id
					 AND (
								from_nodes_ways.position = to_node_ways.position - 1
							OR (from_nodes_ways.position = to_node_ways.position + 1 AND target_ways.oneway = false)
						)
			JOIN nodes_ways_speeds ON
					from_nodes_ways.id = nodes_ways_speeds.from_node_ways_id
				AND to_node_ways.id = nodes_ways_speeds.to_node_ways_id
			JOIN nodes from_nodes ON from_nodes_ways.node_id = from_nodes.id
			JOIN nodes to_nodes ON to_node_ways.node_id = to_nodes.id
			-- ensure that nodes are within the target area, even if the way reaches outside
			JOIN areas
			    ON areas.id = target_area_id
			   	AND st_within(from_nodes.geom, areas.geom)
				AND st_within(to_nodes.geom, areas.geom);

DROP TABLE target_ways;

RETURN;
END;
$$