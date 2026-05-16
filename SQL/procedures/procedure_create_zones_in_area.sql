CREATE OR REPLACE PROCEDURE create_zones_in_area(
    IN p_area_id smallint,
    IN p_zone_types smallint[] DEFAULT NULL
)
LANGUAGE plpgsql
AS
$$
DECLARE
    zone_count bigint;
    outside_zone_count bigint;
    min_zone_area_overlap real := 0.5;
BEGIN
    DROP TABLE IF EXISTS zones_in_area;

    RAISE NOTICE 'Creating zones in area table for area % with minimum zone overlap %', p_area_id, min_zone_area_overlap;

    CREATE TEMPORARY TABLE zones_in_area ON COMMIT DROP AS
    SELECT
        zones.id,
        zones.type,
        zones.geom
    FROM zones
    JOIN areas
        ON areas.id = p_area_id
        AND st_intersects(areas.geom, zones.geom)
        AND (
            p_zone_types IS NULL
            OR cardinality(p_zone_types) = 0
            OR zones.type = ANY(p_zone_types)
        )
        AND (
            st_area(st_intersection(areas.geom, zones.geom)::geography)
            / NULLIF(st_area(zones.geom::geography), 0)
        ) >= min_zone_area_overlap;

    SELECT count(1) INTO zone_count FROM zones_in_area;
    RAISE NOTICE 'Created zones in area table with % zones. Generating indexes.', zone_count;

    CREATE INDEX zones_in_area_id_idx ON zones_in_area(id);
    CREATE INDEX zones_in_area_id_type_idx ON zones_in_area(id, type);
    ANALYZE zones_in_area;

    SELECT count(DISTINCT used_zones.zone_id)
    INTO outside_zone_count
    FROM (
        SELECT oz.id AS zone_id, oz.type AS zone_type
        FROM selected_demand
        JOIN zones AS oz
            ON selected_demand.origin = oz.id
            AND (
                p_zone_types IS NULL
                OR cardinality(p_zone_types) = 0
                OR oz.type = ANY(p_zone_types)
            )
        UNION
        SELECT dz.id AS zone_id, dz.type AS zone_type
        FROM selected_demand
        JOIN zones AS dz
            ON selected_demand.destination = dz.id
            AND (
                p_zone_types IS NULL
                OR cardinality(p_zone_types) = 0
                OR dz.type = ANY(p_zone_types)
            )
    ) AS used_zones
    LEFT JOIN zones_in_area
        ON zones_in_area.id = used_zones.zone_id
        AND zones_in_area.type = used_zones.zone_type
    WHERE zones_in_area.id IS NULL;

    IF outside_zone_count > 0 THEN
        RAISE NOTICE '% zones will be ignored because less than 50%% of their area is inside the selected area.', outside_zone_count;
    END IF;
END;
$$;
