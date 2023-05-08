SELECT
    speed,
    tags->'highway' AS highway,
    tags->'rgt_max_speed' AS posted_speed
FROM nodes_ways_speeds
JOIN nodes_ways from_node_ways
    ON from_node_ways.id = nodes_ways_speeds.from_node_ways_id
   	AND quality IN(1,2)
JOIN nodes_ways to_node_ways
    ON to_node_ways.id = nodes_ways_speeds.to_node_ways_id
    AND from_node_ways.way_id = to_node_ways.way_id
JOIN ways ON ways.id = from_node_ways.way_id
