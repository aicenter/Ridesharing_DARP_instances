CREATE OR REPLACE FUNCTION validate_selected_demand_zones(
    IN p_zone_types smallint[] DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS
$$
DECLARE
    missing_zone_ids bigint[];
    ambiguous_zone_ids bigint[];
BEGIN
    RAISE NOTICE 'Checking that zones exist for demand origin/destination zone ids.';

    SELECT array_agg(zone_id ORDER BY zone_id)
    INTO missing_zone_ids
    FROM (
        SELECT DISTINCT origin AS zone_id
        FROM selected_demand
        WHERE NOT EXISTS (
            SELECT 1
            FROM zones AS oz
            WHERE oz.id = selected_demand.origin
                AND (
                    p_zone_types IS NULL
                    OR cardinality(p_zone_types) = 0
                    OR oz.type = ANY(p_zone_types)
                )
        )
        UNION
        SELECT DISTINCT destination AS zone_id
        FROM selected_demand
        WHERE NOT EXISTS (
            SELECT 1
            FROM zones AS dz
            WHERE dz.id = selected_demand.destination
                AND (
                    p_zone_types IS NULL
                    OR cardinality(p_zone_types) = 0
                    OR dz.type = ANY(p_zone_types)
                )
        )
    ) AS missing_zones;

    IF missing_zone_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Some demand origin/destination zone ids have no matching zones for the requested zone types: %.',
            missing_zone_ids;
    END IF;

    RAISE NOTICE 'Checking that zones are not ambiguous.';

    SELECT array_agg(zone_id ORDER BY zone_id)
    INTO ambiguous_zone_ids
    FROM (
        SELECT used_zones.zone_id
        FROM (
            SELECT DISTINCT origin AS zone_id FROM selected_demand
            UNION
            SELECT DISTINCT destination AS zone_id FROM selected_demand
        ) AS used_zones
        JOIN zones
            ON zones.id = used_zones.zone_id
            AND (
                p_zone_types IS NULL
                OR cardinality(p_zone_types) = 0
                OR zones.type = ANY(p_zone_types)
            )
        GROUP BY used_zones.zone_id
        HAVING count(1) > 1
    ) AS ambiguous_zones;

    IF ambiguous_zone_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Some demand zone ids match more than one zone. Pass a narrower p_zone_types array. Ambiguous zone ids: %.',
            ambiguous_zone_ids;
    END IF;
END;
$$;
