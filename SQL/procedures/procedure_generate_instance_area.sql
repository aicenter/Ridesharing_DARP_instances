CREATE OR REPLACE PROCEDURE generate_area_for_demand (
	IN area_name varchar,
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
LANGUAGE plpgsql
AS
$$
BEGIN
INSERT INTO areas (name, description, geom)
SELECT
    format('instance area: %s', area_name) AS name,
    format('Relevant area for %s instance computed as a buffered convex hull around active zones', area_name) AS description,
	(SELECT * FROM get_area_for_demand(
		srid_plain,
		dataset_ids,
		zone_types,
		buffer_meters,
		min_requests_in_zone,
		datetime_min,
		datetime_max,
		center_point,
		max_distance_from_center_point_meters
	    )
	);
END;
$$;