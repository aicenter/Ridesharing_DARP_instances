CREATE OR REPLACE FUNCTION sample_trip_time(
    IN p_origin_time timestamp,
    IN p_distribution varchar,
    IN p_time_resolution_minutes real,
    IN p_std_dev_minutes real DEFAULT NULL
)
RETURNS timestamp
LANGUAGE plpgsql
AS
$$
BEGIN
    IF p_origin_time IS NULL THEN
        RAISE EXCEPTION 'p_origin_time must be provided.';
    END IF;

    IF p_time_resolution_minutes IS NULL OR p_time_resolution_minutes <= 0 THEN
        RAISE EXCEPTION 'p_time_resolution_minutes must be positive.';
    END IF;

    RETURN sample_trip_time_in_window(
        p_origin_time - (p_time_resolution_minutes::double precision / 2.0) * INTERVAL '1 minute',
        p_origin_time + (p_time_resolution_minutes::double precision / 2.0) * INTERVAL '1 minute',
        p_distribution,
        p_std_dev_minutes
    );
END;
$$;