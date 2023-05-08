WITH
	speed_records_agg AS (
		SELECT
			AVG(speed)  AS speed,
			AVG(st_dev) AS st_dev,
			from_osm_id,
			to_osm_id
		FROM
			speed_records
		WHERE
			EXTRACT(HOUR FROM datetime) = 18
		  	AND EXTRACT(ISODOW FROM datetime) = 5
		GROUP BY from_osm_id, to_osm_id
	)
SELECT
    from_osm_id,
    to_osm_id
-- 	count(1)
FROM speed_records_agg
	LEFT JOIN nodes from_nodes ON from_nodes.osm_id = from_osm_id
WHERE from_nodes.id IS NULL
-- 	JOIN nodes to_nodes ON to_nodes.osm_id = to_osm_id
