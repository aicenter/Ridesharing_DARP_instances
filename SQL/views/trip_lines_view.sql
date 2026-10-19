--
-- Name: trip_lines_view; Type: VIEW; Schema: public
--
-- Demand with sampled positions as straight lines from the origin to the destination node,
-- e.g., for display as arrows in QGIS (line layer with the "Arrow" symbol layer type).
--
-- row_number numbers the requests within each dataset and trip location set (ordered by request id),
-- so subsampling is possible with a layer filter, e.g., every tenth request:
--     "dataset" = 9 AND "set" = 3 AND "row_number" % 10 = 0
-- Requests with the same origin and destination node have zero-length lines (same_node = true).
--

CREATE OR REPLACE VIEW public.trip_lines_view AS
SELECT
    row_number() OVER (ORDER BY demand.dataset, trip_locations.set, demand.id) AS id,
    row_number() OVER (PARTITION BY demand.dataset, trip_locations.set ORDER BY demand.id) AS row_number,
    demand.id AS request_id,
    demand.dataset,
    trip_locations.set,
    demand.source_id,
    demand.origin AS origin_zone,
    demand.destination AS destination_zone,
    demand.origin_time,
    trip_locations.origin AS origin_node,
    trip_locations.destination AS destination_node,
    trip_locations.origin = trip_locations.destination AS same_node,
    st_distance(origin_nodes.geom::geography, destination_nodes.geom::geography) AS distance_m,
    st_makeline(origin_nodes.geom, destination_nodes.geom)::geometry(LineString, 4326) AS geom
FROM public.demand
JOIN public.trip_locations ON trip_locations.request_id = demand.id
JOIN public.nodes AS origin_nodes ON trip_locations.origin = origin_nodes.id
JOIN public.nodes AS destination_nodes ON trip_locations.destination = destination_nodes.id;
