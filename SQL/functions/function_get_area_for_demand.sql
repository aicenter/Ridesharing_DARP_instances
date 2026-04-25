CREATE OR REPLACE FUNCTION get_area_for_demand(
	IN srid_plain integer,
	IN dataset_ids smallint[],
	IN zone_types smallint[],
	IN buffer_meters smallint = 1000,
	IN min_requests_in_zone smallint = 1,
	IN datetime_min timestamp = '2000-01-01 00:00:00',
	IN datetime_max timestamp = '2100-01-01 00:00:00',
	IN center_point geometry = NULL,
	IN max_distance_from_center_point_meters smallint = 10000
)
RETURNS geometry
LANGUAGE plpgsql
AS
$$
DECLARE
	target_area geometry;
BEGIN
    IF center_point IS NULL THEN
		RAISE NOTICE 'Filtering zones of types %', zone_types;
	ELSE
		RAISE NOTICE 'Filtering zones of types % within a % distance from: %', zone_types, max_distance_from_center_point_meters, center_point;
	END IF;

    CREATE TEMPORARY TABLE filtered_zones AS
    SELECT *
    FROM zones
    WHERE
        type = ANY(zone_types)
    	AND center_point IS NULL
       		OR st_distance(center_point, st_transform(geom, srid_plain)) <= max_distance_from_center_point_meters;
    CREATE INDEX filtered_zones_geom_idx ON filtered_zones(id);
    RAISE NOTICE 'Filtered zones count: %', (SELECT count(1) FROM filtered_zones);

	RAISE NOTICE 'Generating area around filtered zones with request count higher than %. The requests needs to satisfy
	    the following conditions:
	    	datetime between % and %,
	    	dataset one of the: %
	    The buffer is set to % m', min_requests_in_zone, datetime_min, datetime_max,
	    	(SELECT name FROM dataset WHERE id = ANY(dataset_ids)), buffer_meters;
	SELECT
		st_multi(st_transform(st_buffer(st_convexhull(st_collect(st_transform(geom, srid_plain))), buffer_meters), 4326))
			INTO target_area
	FROM (
		SELECT geom FROM (
			SELECT geom, request_count
				FROM filtered_zones
				JOIN LATERAL (
					SELECT count(1) AS request_count
						FROM demand
						WHERE
							dataset = ANY(dataset_ids)
							AND filtered_zones.id = demand.destination
							AND origin_time BETWEEN datetime_min AND datetime_max
						LIMIT min_requests_in_zone
				) demand ON request_count > 0
			UNION
			SELECT geom, request_count
				FROM filtered_zones
				JOIN LATERAL (
					SELECT count(1) AS request_count
						FROM demand
						WHERE
							dataset = ANY(dataset_ids)
							AND filtered_zones.id = demand.origin
							AND origin_time BETWEEN datetime_min AND datetime_max
						LIMIT min_requests_in_zone
				) demand ON request_count > 0
		) AS active_zones
		GROUP BY geom
		HAVING sum(request_count) >= min_requests_in_zone
	) AS active_zones;

	DROP TABLE IF EXISTS filtered_zones;

    RETURN target_area;
END;
$$;
