SELECT name,
       ST_area(st_transform(geom, srid)) / 1000000 AS area_km2

--     st_srid(geom)
FROM areas
JOIN (SELECT 12 AS id, 32618 AS srid
      UNION ALL
      SELECT 4 AS id, 32618 AS srid
      UNION ALL
      SELECT 19 AS id, 26916 AS srid
      UNION ALL
      SELECT 22 AS id, 32618 AS srid) AS srids
     ON areas.id = srids.id
JOIN (SELECT 12 AS id, (2, 3, 4, 5) AS dataset_id
      UNION ALL
      SELECT 4 AS id, (2, 3, 4, 5) AS dataset_id
      UNION ALL
      SELECT 19 AS id, (1) AS dataset_id
      UNION ALL
      SELECT 22 AS id, (7) AS dataset_id) AS dataset_ids
     ON areas.id = dataset_ids.id
JOIN demand
    ON demand.dataset_id IN dataset_ids.dataset_id
