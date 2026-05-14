CREATE OR REPLACE FUNCTION get_non_sampled_demand_in_area(area_id smallint)
RETURNS SETOF demand
LANGUAGE SQL
BEGIN ATOMIC
WITH demand_area AS (
SELECT geom FROM areas WHERE id = area_id
)
SELECT demand.* FROM demand
JOIN zones AS origin_zones ON demand.origin = origin_zones.id
JOIN zones AS destination_zones ON demand.destination = destination_zones.id
JOIN demand_area ON st_within(origin_zones.geom, demand_area.geom) AND st_within(destination_zones.geom, demand_area.geom);
END;