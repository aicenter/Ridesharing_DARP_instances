-- CREATE TEMPORARY TABLE area_data (
--     id INTEGER PRIMARY KEY,
--     srid INTEGER,
--     dataset_ids integer[],
--     zone_types integer[]
-- );
--
-- INSERT INTO area_data (id, srid, dataset_ids, zone_types)
-- VALUES (12, 32618, ARRAY[2, 3, 4, 5], ARRAY[2]),
--        (4, 32618, ARRAY[2, 3, 4, 5], ARRAY[2]),
--        (19, 26916, ARRAY[1], ARRAY[0, 1]),
--        (22, 32618, ARRAY[7], ARRAY[4]);


SELECT
    name,
    ST_area(st_transform(geom, max(area_data.srid))) / 1000000 AS area_km2,
    count(1) AS demand_count,
    count(1) / (ST_area(st_transform(geom, max(area_data.srid))) / 1000000)  AS demand_density,
    max(zone_agg_data.avg_zone_area_km2) AS avg_zone_area_km2
--     st_srid(geom)
FROM areas
JOIN area_data
     ON areas.id = area_data.id
JOIN demand
    ON demand.dataset = ANY(area_data.dataset_ids)
    AND demand.origin_time BETWEEN '2022-04-05 18:00:00' AND '2022-04-05 18:59:59'
JOIN LATERAL (
    SELECT avg(st_area(st_transform(geom, area_data.srid))) / 1000000 AS avg_zone_area_km2
    FROM zones
    WHERE zones.type = ANY(area_data.zone_types)
    AND ST_Intersects(areas.geom, zones.geom)
) AS zone_agg_data ON TRUE
GROUP BY areas.id
;

-- DROP TABLE area_data;