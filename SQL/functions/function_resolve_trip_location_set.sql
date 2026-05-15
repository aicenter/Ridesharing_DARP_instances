CREATE OR REPLACE FUNCTION resolve_trip_location_set(
    IN p_trip_location_set_id integer DEFAULT NULL,
    IN p_trip_location_set_description varchar DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
AS
$$
DECLARE
    resolved_id integer;
    resolved_description varchar;
BEGIN
    IF p_trip_location_set_id IS NULL AND p_trip_location_set_description IS NULL THEN
        RAISE EXCEPTION 'Either p_trip_location_set_id or p_trip_location_set_description must be provided.';
    END IF;

    IF p_trip_location_set_id IS NOT NULL AND p_trip_location_set_description IS NOT NULL THEN
        RAISE EXCEPTION 'Provide only one of p_trip_location_set_id or p_trip_location_set_description.';
    END IF;

    IF p_trip_location_set_id IS NOT NULL THEN
        SELECT id
        INTO resolved_id
        FROM trip_location_sets
        WHERE id = p_trip_location_set_id;

        IF resolved_id IS NULL THEN
            RAISE EXCEPTION 'trip_location_sets.id=% does not exist.', p_trip_location_set_id;
        END IF;

        RETURN resolved_id;
    END IF;

    resolved_description := btrim(p_trip_location_set_description);

    IF resolved_description = '' THEN
        RAISE EXCEPTION 'p_trip_location_set_description must be non-empty.';
    END IF;

    INSERT INTO trip_location_sets (description)
    VALUES (resolved_description)
    RETURNING id INTO resolved_id;

    RETURN resolved_id;
END;
$$;
