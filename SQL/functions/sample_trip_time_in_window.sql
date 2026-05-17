CREATE OR REPLACE FUNCTION sample_trip_time_in_window(
    IN p_window_start_time timestamp,
    IN p_window_end_time timestamp,
    IN p_distribution varchar,
    IN p_std_dev_minutes real DEFAULT NULL
)
RETURNS timestamp
LANGUAGE plpgsql
AS
$$
DECLARE
    distribution varchar := replace(replace(lower(btrim(p_distribution)), '-', '_'), ' ', '_');
    window_minutes double precision;
    std_dev_minutes double precision;
    standard_normal double precision;
    offset_minutes double precision;
    midpoint_time timestamp;
    attempt integer;
BEGIN
    IF p_window_start_time IS NULL OR p_window_end_time IS NULL THEN
        RAISE EXCEPTION 'p_window_start_time and p_window_end_time must be provided.';
    END IF;

    IF p_window_start_time > p_window_end_time THEN
        RAISE EXCEPTION 'p_window_start_time (%) must be before or equal to p_window_end_time (%).',
            p_window_start_time, p_window_end_time;
    END IF;

    IF distribution IS NULL OR distribution = '' THEN
        RAISE EXCEPTION 'p_distribution must be provided.';
    END IF;

    window_minutes := extract(epoch FROM (p_window_end_time - p_window_start_time)) / 60.0;

    IF window_minutes = 0 THEN
        RETURN p_window_start_time;
    END IF;

    IF distribution = 'uniform' THEN
        RETURN p_window_start_time + (random() * window_minutes) * INTERVAL '1 minute';
    END IF;

    IF distribution = 'truncated_normal' THEN
        midpoint_time := p_window_start_time + (window_minutes / 2.0) * INTERVAL '1 minute';
        std_dev_minutes := coalesce(
            p_std_dev_minutes::double precision,
            window_minutes / 6.0
        );

        IF std_dev_minutes <= 0 THEN
            RAISE EXCEPTION 'p_std_dev_minutes must be positive when provided.';
        END IF;

        FOR attempt IN 1..100 LOOP
            standard_normal :=
                sqrt(-2.0 * ln(greatest(random(), 1e-12::double precision)))
                * cos(2.0 * pi() * random());
            offset_minutes := standard_normal * std_dev_minutes;

            IF offset_minutes BETWEEN (-window_minutes / 2.0) AND (window_minutes / 2.0) THEN
                RETURN midpoint_time + offset_minutes * INTERVAL '1 minute';
            END IF;
        END LOOP;

        RETURN midpoint_time + greatest(
            -window_minutes / 2.0,
            least(window_minutes / 2.0, offset_minutes)
        ) * INTERVAL '1 minute';
    END IF;

    RAISE EXCEPTION 'Unsupported trip time distribution: %. Supported distributions: uniform, truncated_normal.',
        p_distribution;
END;
$$;
