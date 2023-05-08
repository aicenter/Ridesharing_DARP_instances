WITH v_result AS (
    SELECT st_intersection(
            (st_dump(
                    st_voronoipolygons(st_collect((centroid)))
                )).geom,
            (SELECT geom FROM areas WHERE id = 22)
        ) AS geom
    FROM address_block
)
INSERT INTO zones
SELECT id, name, st_multi(geom), 4 AS type
FROM
    v_result
    JOIN address_block
        ON st_within(address_block.centroid, v_result.geom)