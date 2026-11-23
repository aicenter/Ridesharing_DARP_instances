------------------------------------------------------------------------------------------------------------------------
-- Selects one representative road network node for each zone in zones_in_area. The representative stands for the
-- whole zone in zone-to-zone travel time computations (see compute_speed_factor), so it should be a well accessible
-- node near the middle of the zone.
--
-- Candidates are the nodes that the demand position sampling can pick: the start nodes of demand_sampling_edges
-- (no motorways and trunks, largest strong component of the area) that lie within the zone.
-- Among the candidates within a circle around the zone centroid, the one with the highest
-- min(in-degree, out-degree) is selected, the nearest to the centroid on ties. The radius of the circle is half the
-- radius of a circle with the area of the zone. If the circle contains no candidate (the centroid is in a park, in
-- water, or outside a concave zone), the candidate nearest to the centroid is selected.
-- Zones without any candidate are not returned.
--
-- Parameters:
--      - p_area_id: the area whose edges are used for the node degrees.
--      - p_area_srid: projected SRID of the area, used for the distances (metres).
-- Returns: zone id and type, the representative node and whether it lies in the circle around the centroid.
-- Required temporary tables: zones_in_area (create_zones_in_area), demand_sampling_edges
--      (create_demand_sampling_edges)
-- Required tables: nodes, edges
-- Affected tables: None
------------------------------------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION select_zone_representative_nodes(
    IN p_area_id smallint,
    IN p_area_srid integer
)
RETURNS TABLE (
    zone_id bigint,
    zone_type smallint,
    node_id bigint,
    in_circle boolean
)
LANGUAGE plpgsql
AS
$$
BEGIN
    RETURN QUERY
    WITH candidate_nodes AS (
        SELECT
            nodes.id,
            nodes.geom,
            st_transform(nodes.geom, p_area_srid) AS projected_geom
        FROM (
            SELECT DISTINCT demand_sampling_edges."from" AS id
            FROM demand_sampling_edges
        ) AS sampling_nodes
        JOIN nodes
            ON nodes.id = sampling_nodes.id
    ),
    out_degrees AS (
        SELECT edges."from" AS id, count(1) AS degree
        FROM edges
        WHERE edges.area = p_area_id
        GROUP BY edges."from"
    ),
    in_degrees AS (
        SELECT edges."to" AS id, count(1) AS degree
        FROM edges
        WHERE edges.area = p_area_id
        GROUP BY edges."to"
    ),
    projected_zones AS (
        SELECT
            zones_in_area.id,
            zones_in_area.type,
            zones_in_area.geom,
            st_centroid(st_transform(zones_in_area.geom, p_area_srid)) AS centroid,
            0.5 * sqrt(st_area(st_transform(zones_in_area.geom, p_area_srid)) / pi()) AS radius
        FROM zones_in_area
    ),
    zone_candidates AS (
        SELECT
            projected_zones.id AS candidate_zone_id,
            projected_zones.type AS candidate_zone_type,
            candidate_nodes.id AS candidate_node_id,
            st_distance(candidate_nodes.projected_geom, projected_zones.centroid) AS centroid_distance,
            st_distance(candidate_nodes.projected_geom, projected_zones.centroid)
                <= projected_zones.radius AS candidate_in_circle,
            least(coalesce(out_degrees.degree, 0), coalesce(in_degrees.degree, 0)) AS min_degree
        FROM projected_zones
        JOIN candidate_nodes
            ON st_within(candidate_nodes.geom, projected_zones.geom)
        LEFT JOIN out_degrees
            ON out_degrees.id = candidate_nodes.id
        LEFT JOIN in_degrees
            ON in_degrees.id = candidate_nodes.id
    ),
    ranked_candidates AS (
        SELECT
            zone_candidates.*,
            row_number() OVER (
                PARTITION BY zone_candidates.candidate_zone_id, zone_candidates.candidate_zone_type
                ORDER BY
                    zone_candidates.candidate_in_circle DESC,
                    -- the degree decides only within the circle
                    CASE WHEN zone_candidates.candidate_in_circle THEN zone_candidates.min_degree ELSE 0 END DESC,
                    zone_candidates.centroid_distance,
                    zone_candidates.candidate_node_id
            ) AS candidate_rank
        FROM zone_candidates
    )
    SELECT
        ranked_candidates.candidate_zone_id,
        ranked_candidates.candidate_zone_type,
        ranked_candidates.candidate_node_id,
        ranked_candidates.candidate_in_circle
    FROM ranked_candidates
    WHERE ranked_candidates.candidate_rank = 1
    ORDER BY ranked_candidates.candidate_zone_id, ranked_candidates.candidate_zone_type;
END;
$$;
