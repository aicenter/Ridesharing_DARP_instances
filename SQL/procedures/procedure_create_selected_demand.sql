CREATE OR REPLACE PROCEDURE create_selected_demand(
    IN p_demand_dataset_ids integer[],
    IN p_start_time timestamp DEFAULT NULL,
    IN p_end_time timestamp DEFAULT NULL,
    IN p_ignored_zones bigint[] DEFAULT NULL
)
LANGUAGE plpgsql
AS
$$
DECLARE
    filter_descriptions text[];
    trip_count bigint;
BEGIN
    IF p_demand_dataset_ids IS NULL OR cardinality(p_demand_dataset_ids) = 0 THEN
        RAISE EXCEPTION 'p_demand_dataset_ids must contain at least one dataset id.';
    END IF;

    DROP TABLE IF EXISTS selected_demand;

    filter_descriptions := ARRAY[
        format('dataset in [%s]', array_to_string(p_demand_dataset_ids, ', '))
    ];

    IF p_start_time IS NOT NULL THEN
        filter_descriptions := array_append(
            filter_descriptions,
            format('origin_time >= %s', p_start_time)
        );
    END IF;

    IF p_end_time IS NOT NULL THEN
        filter_descriptions := array_append(
            filter_descriptions,
            format('origin_time <= %s', p_end_time)
        );
    END IF;

    IF p_ignored_zones IS NOT NULL AND cardinality(p_ignored_zones) > 0 THEN
        filter_descriptions := array_append(
            filter_descriptions,
            format('origin and destination not in ignored zones [%s]', array_to_string(p_ignored_zones, ', '))
        );
    END IF;

    RAISE NOTICE 'Creating selected demand table with filters: %', array_to_string(filter_descriptions, '; ');

    CREATE TEMPORARY TABLE selected_demand ON COMMIT DROP AS
        SELECT demand.*
        FROM demand
        WHERE dataset = ANY(p_demand_dataset_ids)
            AND (p_start_time IS NULL OR origin_time >= p_start_time)
            AND (p_end_time IS NULL OR origin_time <= p_end_time)
            AND (
                p_ignored_zones IS NULL
                OR cardinality(p_ignored_zones) = 0
                OR (
                    origin <> ALL(p_ignored_zones)
                    AND destination <> ALL(p_ignored_zones)
                )
            );

    SELECT count(1) INTO trip_count FROM selected_demand;
    RAISE NOTICE 'Selected % demand requests before area filtering. Generating indices.', trip_count;

    CREATE INDEX selected_demand_id_idx ON selected_demand(id);
    CREATE INDEX selected_demand_origin_idx ON selected_demand(origin);
    CREATE INDEX selected_demand_destination_idx ON selected_demand(destination);
    ANALYZE selected_demand;


END;
$$;
