--
-- Name: positions_view; Type: VIEW; Schema: public
--

CREATE OR REPLACE VIEW public.positions_view AS
SELECT
    trip_locations.request_id,
    trip_locations.set,
    origin_nodes.geom AS origin,
    destination_nodes.geom AS destination
FROM public.trip_locations
JOIN public.nodes AS origin_nodes ON trip_locations.origin = origin_nodes.id
JOIN public.nodes AS destination_nodes ON trip_locations.destination = destination_nodes.id;
