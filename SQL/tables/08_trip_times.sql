--
-- Name: trip_times; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.trip_times (
    request_id integer NOT NULL,
    "time" timestamp without time zone NOT NULL,
    set integer NOT NULL,
    CONSTRAINT trip_times_pk PRIMARY KEY (request_id, set),
    CONSTRAINT fk_trip_times_demand_1 FOREIGN KEY (request_id) REFERENCES public.demand (id),
    CONSTRAINT fk_trip_times_trip_time_sets_1 FOREIGN KEY (set) REFERENCES public.trip_time_sets (id)
);
