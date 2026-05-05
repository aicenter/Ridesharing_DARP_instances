CREATE OR REPLACE VIEW zones_with_demand_destination_counts AS
WITH zones_with_demand_counts AS (
    SELECT zones.id, COUNT(demand.id) AS demand_count
    FROM zones
        JOIN demand ON zones.id = demand.destination
    GROUP BY zones.id
)
SELECT zones_with_demand_counts.*, zones.name as name, zones.geom as geom
FROM zones_with_demand_counts
JOIN zones ON zones_with_demand_counts.id = zones.id;