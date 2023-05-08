SELECT DISTINCT osm_id FROM (
	SELECT from_osm_id AS osm_id
	FROM speed_records WHERE dataset = 1 AND datetime BETWEEN '2020-03-01' AND '2020-03-31'
	UNION
	SELECT to_osm_id AS osm_id
	FROM speed_records WHERE dataset = 1 AND datetime BETWEEN '2020-03-01' AND '2020-03-31'
	UNION
	SELECT from_osm_id AS osm_id
	FROM speed_records_quarterly WHERE dataset = 1 AND year = 2020 AND quarter = 1
	UNION
	SELECT to_osm_id AS osm_id
	FROM speed_records_quarterly WHERE dataset = 1  AND year = 2020 AND quarter = 1
) AS osm_ids
ORDER BY osm_id