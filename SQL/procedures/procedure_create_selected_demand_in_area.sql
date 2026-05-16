CREATE OR REPLACE PROCEDURE create_selected_demand_in_area()
LANGUAGE plpgsql
AS
$$
DECLARE
    demand_count bigint;
    outside_request_count bigint;
BEGIN
    DROP TABLE IF EXISTS selected_demand_in_area;

    RAISE NOTICE 'Creating selected demand in area table from zones_in_area';

    CREATE TEMPORARY TABLE selected_demand_in_area ON COMMIT DROP AS
    SELECT
        selected_demand.*,
        oz.id AS origin_zone_id,
        oz.geom AS origin_zone_geom,
        dz.id AS destination_zone_id,
        dz.geom AS destination_zone_geom
    FROM selected_demand
    JOIN zones_in_area AS oz
        ON selected_demand.origin = oz.id
    JOIN zones_in_area AS dz
        ON selected_demand.destination = dz.id;

    SELECT count(1) INTO demand_count FROM selected_demand_in_area;
    RAISE NOTICE 'Created selected demand in area table with % requests. Generating id index.', demand_count;

    CREATE INDEX selected_demand_in_area_id_idx ON selected_demand_in_area(id);
    ANALYZE selected_demand_in_area;

    SELECT count(1)
    INTO outside_request_count
    FROM selected_demand
    LEFT JOIN selected_demand_in_area
        ON selected_demand_in_area.id = selected_demand.id
    WHERE selected_demand_in_area.id IS NULL;

    IF outside_request_count > 0 THEN
        RAISE NOTICE '% requests will be ignored because their origin or destination zone is outside the selected area threshold.', outside_request_count;
    END IF;
END;
$$;
