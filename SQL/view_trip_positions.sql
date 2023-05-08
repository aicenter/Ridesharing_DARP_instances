CREATE OR REPLACE VIEW positions_view AS(
SELECT
    trip_locations.request_id,
    trip_locations.set,
    origin_nodes.geom AS origin,
    destination_nodes.geom AS destination
FROM trip_locations
JOIN nodes origin_nodes ON trip_locations.origin = origin_nodes.id
JOIN nodes destination_nodes ON trip_locations.destination = destination_nodes.id
)