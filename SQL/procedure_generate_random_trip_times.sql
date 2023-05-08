CREATE PROCEDURE generate_random_trip_times(demand_dataset integer, trip_time_set integer, time_resolution real, start_time date DEFAULT NULL::date, end_time date DEFAULT NULL::date)
	LANGUAGE plpgsql
AS
$$BEGIN
	INSERT INTO trip_times (request_id, time, set)
	SELECT 
		id, 
		origin_time - 0.5 * time_resolution * INTERVAL '1 minute' + random() * time_resolution * INTERVAL '1 minute',
		trip_time_set
	FROM demand 
	WHERE dataset = demand_dataset
		AND start_time IS NULL OR origin_time BETWEEN start_time AND end_time;
END$$;

ALTER PROCEDURE generate_random_trip_times(integer, integer, real, date, date) OWNER TO fiedler;

