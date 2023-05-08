CREATE OR REPLACE FUNCTION select_network_nodes_in_area(area_id smallint)
RETURNS TABLE(index integer, id bigint, x float, y float, geom geometry)
LANGUAGE sql
AS
$$
SELECT
	(row_number() over () - 1)::integer AS index,
	nodes.id AS id,
	st_x(nodes.geom) AS x,
	st_y(nodes.geom) AS y,
	nodes.geom as geom
	FROM nodes
	JOIN component_data
		ON component_data.node_id = nodes.id
		   	AND component_data.area = area_id
			AND component_data.component_id = 0
			AND nodes.contracted = FALSE
ORDER BY nodes.id;
$$