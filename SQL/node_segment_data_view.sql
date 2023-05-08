CREATE OR REPLACE VIEW node_segment_data AS
SELECT
    row_number() OVER () AS id,
    st_makeline(from_nodes.geom, to_nodes.geom) as geom, nodes_ways_speeds.speed, quality
FROM nodes_ways_speeds
JOIN nodes_ways from_nodes_ways ON nodes_ways_speeds.from_node_ways_id = from_nodes_ways.id
JOIN nodes_ways to_nodes_ways ON nodes_ways_speeds.to_node_ways_id = to_nodes_ways.id
JOIN nodes from_nodes ON from_nodes_ways.node_id = from_nodes.id
JOIN nodes to_nodes ON to_nodes_ways.node_id = to_nodes.id


