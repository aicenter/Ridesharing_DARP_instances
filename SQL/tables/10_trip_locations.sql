--
-- Name: trip_locations; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.trip_locations (
    request_id integer NOT NULL,
    origin bigint NOT NULL,
    destination bigint NOT NULL,
    set integer NOT NULL,
    CONSTRAINT trip_locations_pk PRIMARY KEY (request_id, set),
    CONSTRAINT fk_trip_locations_demand_1 FOREIGN KEY (request_id) REFERENCES public.demand (id),
    CONSTRAINT fk_trip_locations_trip_location_sets_1 FOREIGN KEY (set) REFERENCES public.trip_location_sets (id),
    CONSTRAINT trip_locations_origin_nodes_id_fk FOREIGN KEY (origin) REFERENCES public.nodes (id),
    CONSTRAINT trip_locations_destination_nodes_id_fk FOREIGN KEY (destination) REFERENCES public.nodes (id)
);


CREATE INDEX IF NOT EXISTS trip_locations_destination_index ON public.trip_locations USING btree (destination);
CREATE INDEX IF NOT EXISTS trip_locations_origin_index ON public.trip_locations USING btree (origin);
