CREATE OR REPLACE PROCEDURE generate_trip_times(
    IN p_trip_location_set_id integer,
    IN p_trip_time_set_id integer DEFAULT NULL,
    IN p_trip_time_set_description varchar DEFAULT NULL,
    IN p_demand_dataset_ids integer[] DEFAULT NULL,
    IN p_time_mode varchar DEFAULT 'around_origin_time',
    IN p_filter_start_time timestamp DEFAULT NULL,
    IN p_filter_end_time timestamp DEFAULT NULL,
    IN p_sample_start_time timestamp DEFAULT NULL,
    IN p_sample_end_time timestamp DEFAULT NULL,
    IN p_distribution varchar DEFAULT 'uniform',
    IN p_time_resolution_minutes real DEFAULT 60,
    IN p_std_dev_minutes real DEFAULT NULL
)
LANGUAGE plpgsql
AS
$$
DECLARE
    v_trip_time_set_id integer;
    selected_request_count bigint;
    existing_trip_time_count bigint;
    inserted_count bigint;
    null_origin_time_count bigint;
    filter_descriptions text[];
    mode varchar := replace(replace(lower(btrim(p_time_mode)), '-', '_'), ' ', '_');
    distribution varchar := replace(replace(lower(btrim(p_distribution)), '-', '_'), ' ', '_');
BEGIN
    IF p_trip_location_set_id IS NULL THEN
        RAISE EXCEPTION 'p_trip_location_set_id must be provided.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM trip_location_sets WHERE id = p_trip_location_set_id) THEN
        RAISE EXCEPTION 'trip_location_sets.id=% does not exist.', p_trip_location_set_id;
    END IF;

    IF p_filter_start_time IS NOT NULL AND p_filter_end_time IS NOT NULL AND p_filter_start_time > p_filter_end_time THEN
        RAISE EXCEPTION 'p_filter_start_time (%) must be before or equal to p_filter_end_time (%).',
            p_filter_start_time, p_filter_end_time;
    END IF;

    IF mode IS NULL OR mode = '' THEN
        RAISE EXCEPTION 'p_time_mode must be provided.';
    END IF;

    IF mode IN ('around_origin', 'origin_time', 'demand_origin_time') THEN
        mode := 'around_origin_time';
    ELSIF mode IN ('between', 'between_time', 'absolute_window') THEN
        mode := 'between_times';
    END IF;

    IF mode NOT IN ('around_origin_time', 'between_times') THEN
        RAISE EXCEPTION 'Unsupported trip time mode: %. Supported modes: around_origin_time, between_times.',
            p_time_mode;
    END IF;

    IF distribution IS NULL OR distribution = '' THEN
        RAISE EXCEPTION 'p_distribution must be provided.';
    END IF;

    IF distribution NOT IN ('uniform', 'truncated_normal') THEN
        RAISE EXCEPTION 'Unsupported trip time distribution: %. Supported distributions: uniform, truncated_normal.',
            p_distribution;
    END IF;

    IF mode = 'around_origin_time' THEN
        IF p_time_resolution_minutes IS NULL OR p_time_resolution_minutes <= 0 THEN
            RAISE EXCEPTION 'p_time_resolution_minutes must be positive for around_origin_time mode.';
        END IF;
    END IF;

    IF mode = 'between_times' THEN
        IF p_sample_start_time IS NULL OR p_sample_end_time IS NULL THEN
            RAISE EXCEPTION 'p_sample_start_time and p_sample_end_time must be provided for between_times mode.';
        END IF;

        IF p_sample_start_time > p_sample_end_time THEN
            RAISE EXCEPTION 'p_sample_start_time (%) must be before or equal to p_sample_end_time (%).',
                p_sample_start_time, p_sample_end_time;
        END IF;
    END IF;

    v_trip_time_set_id := resolve_trip_time_set(
        p_trip_time_set_id,
        p_trip_time_set_description
    );
    RAISE NOTICE 'Using trip_time_sets.id=%.', v_trip_time_set_id;

    IF mode = 'around_origin_time' THEN
        RAISE NOTICE 'Generating trip times using mode %, distribution %, resolution % minutes, std_dev % minutes.',
            mode, distribution, p_time_resolution_minutes, coalesce(p_std_dev_minutes::text, 'default');
    ELSE
        RAISE NOTICE 'Generating trip times using mode %, distribution %, std_dev % minutes.',
            mode, distribution, coalesce(p_std_dev_minutes::text, 'default');
    END IF;

    filter_descriptions := ARRAY[
        format('trip_location_set = %s', p_trip_location_set_id)
    ];

    IF p_demand_dataset_ids IS NOT NULL AND cardinality(p_demand_dataset_ids) > 0 THEN
        filter_descriptions := array_append(
            filter_descriptions,
            format('dataset in [%s]', array_to_string(p_demand_dataset_ids, ', '))
        );
    END IF;

    IF p_filter_start_time IS NOT NULL THEN
        filter_descriptions := array_append(
            filter_descriptions,
            format('origin_time >= %s', p_filter_start_time)
        );
    END IF;

    IF p_filter_end_time IS NOT NULL THEN
        filter_descriptions := array_append(
            filter_descriptions,
            format('origin_time <= %s', p_filter_end_time)
        );
    END IF;

    IF mode = 'between_times' THEN
        RAISE NOTICE 'Sampling trip times between % and %.', p_sample_start_time, p_sample_end_time;
    END IF;

    RAISE NOTICE 'Creating selected trip time request table with filters: %',
        array_to_string(filter_descriptions, '; ');

    DROP TABLE IF EXISTS selected_trip_time_requests;
    CREATE TEMPORARY TABLE selected_trip_time_requests ON COMMIT DROP AS
        SELECT demand.id, demand.origin_time
        FROM demand
        JOIN trip_locations
            ON trip_locations.request_id = demand.id
            AND trip_locations.set = p_trip_location_set_id
        WHERE (
                p_demand_dataset_ids IS NULL
                OR cardinality(p_demand_dataset_ids) = 0
                OR demand.dataset = ANY(p_demand_dataset_ids)
            )
            AND (p_filter_start_time IS NULL OR demand.origin_time >= p_filter_start_time)
            AND (p_filter_end_time IS NULL OR demand.origin_time <= p_filter_end_time);

    CREATE INDEX selected_trip_time_requests_id_idx ON selected_trip_time_requests(id);
    ANALYZE selected_trip_time_requests;

    SELECT count(1) INTO selected_request_count FROM selected_trip_time_requests;

    RAISE NOTICE 'Selected % requests with sampled positions for trip time generation.', selected_request_count;

    IF mode = 'around_origin_time' THEN
        SELECT count(1)
        INTO null_origin_time_count
        FROM selected_trip_time_requests
        WHERE origin_time IS NULL;

        IF null_origin_time_count > 0 THEN
            RAISE EXCEPTION '% selected requests have NULL origin_time. Use between_times mode or filter them out.',
                null_origin_time_count;
        END IF;
    END IF;

    SELECT count(1)
        INTO existing_trip_time_count
        FROM trip_times
        JOIN selected_trip_time_requests
            ON selected_trip_time_requests.id = trip_times.request_id
        WHERE trip_times.set = v_trip_time_set_id;

    IF existing_trip_time_count > 0 THEN
        RAISE EXCEPTION '% trip_times rows already exist for trip_time_sets.id=% and the selected requests.',
            existing_trip_time_count, v_trip_time_set_id;
    END IF;

    IF mode = 'around_origin_time' THEN
        INSERT INTO trip_times (request_id, "time", set)
        SELECT
            selected_trip_time_requests.id,
            sample_trip_time(
                selected_trip_time_requests.origin_time,
                distribution,
                p_time_resolution_minutes,
                p_std_dev_minutes
            ) AS "time",
            v_trip_time_set_id AS set
        FROM selected_trip_time_requests;
    ELSE
        INSERT INTO trip_times (request_id, "time", set)
        SELECT
            selected_trip_time_requests.id,
            sample_trip_time_in_window(
                p_sample_start_time,
                p_sample_end_time,
                distribution,
                p_std_dev_minutes
            ) AS "time",
            v_trip_time_set_id AS set
        FROM selected_trip_time_requests;
    END IF;

    GET DIAGNOSTICS inserted_count = ROW_COUNT;

    IF inserted_count <> selected_request_count THEN
        RAISE EXCEPTION 'Inserted % trip_times rows, but % requests were selected.',
            inserted_count, selected_request_count;
    END IF;

    RAISE NOTICE 'Inserted % trip_times rows for trip_time_sets.id=%.', inserted_count, v_trip_time_set_id;

    DROP TABLE IF EXISTS selected_trip_time_requests;
END;
$$;
