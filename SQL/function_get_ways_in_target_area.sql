CREATE OR REPLACE FUNCTION get_ways_in_target_area(IN target_area_id smallint)
RETURNS table(id bigint, tags hstore, geom geometry, area integer, "from" bigint, "to" bigint, oneway boolean)
LANGUAGE sql
AS $$
	SELECT ways.*
	        FROM ways
	            JOIN areas ON areas.id = target_area_id AND st_intersects(areas.geom, ways.geom);
$$