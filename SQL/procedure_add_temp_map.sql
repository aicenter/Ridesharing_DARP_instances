CREATE PROCEDURE add_temp_map(map_area integer)
	LANGUAGE plpgsql
AS
$$BEGIN
    DELETE FROM ways WHERE area = map_area;
    DELETE FROM nodes WHERE area = map_area;
	DELETE FROM nodes_ways WHERE area = map_area;
    INSERT INTO nodes (id, geom, area) SELECT osm_id, geom, map_area FROM nodes_tmp ON CONFLICT DO NOTHING;
	INSERT INTO ways (id, tags, geom, "from", "to", area, oneway) 
		SELECT ways_tmp.osm_id, tags, ways_tmp.geom, from_nodes.osm_id, to_nodes.osm_id, map_area, oneway FROM ways_tmp
    	JOIN nodes_tmp from_nodes ON ways_tmp."from" = from_nodes.id
    	JOIN nodes_tmp to_nodes ON ways_tmp."to" = to_nodes.id
    	ON CONFLICT DO NOTHING;
    INSERT INTO nodes_ways (node_id, way_id, position, area) 
    	SELECT nodes_tmp.osm_id, ways_tmp.osm_id, position, map_area FROM nodes_ways_tmp
    	JOIN nodes_tmp ON nodes_ways_tmp.node_id = nodes_tmp.id
    	JOIN ways_tmp ON nodes_ways_tmp.way_id = ways_tmp.id
    	ON CONFLICT DO NOTHING;
END$$;

ALTER PROCEDURE add_temp_map(integer) OWNER TO fiedler;

