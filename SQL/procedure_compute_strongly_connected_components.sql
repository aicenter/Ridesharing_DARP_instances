CREATE OR REPLACE PROCEDURE compute_strong_components(IN target_area_id smallint)
LANGUAGE plpgsql
AS $$
BEGIN

RAISE NOTICE 'Computing strong components for area %', (SELECT name FROM areas WHERE id = target_area_id);
CREATE TEMPORARY TABLE components AS
SELECT * FROM
pgr_strongcomponents(format(
    'WITH target_area AS (SELECT geom FROM areas WHERE id = %L) ' ||
    'SELECT row_number() OVER () AS id, "from" AS source, "to" AS target, 0 AS cost, -1 AS reverse_cost ' ||
    'FROM edges CROSS JOIN target_area WHERE st_within(edges.geom, target_area.geom)', target_area_id
));
RAISE NOTICE 'Strong components computed: % components', (SELECT count(1) OVER () FROM components GROUP BY component LIMIT 1);

RAISE NOTICE 'Storing the results in the component_data table';
WITH agg AS (
	SELECT
		component,
		count(1),
		row_number() OVER (ORDER BY count(1) DESC) - 1 AS id
	FROM
		 components
	GROUP BY component
	ORDER BY count(1) DESC
)
INSERT INTO component_data
SELECT
    id,
    node,
    target_area_id
FROM
    components
	JOIN agg ON components.component = agg.component
	ORDER BY id;

DROP TABLE components;
END
$$