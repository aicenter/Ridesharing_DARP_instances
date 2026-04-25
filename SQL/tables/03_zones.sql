--
-- Name: zones; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.zones (
    id bigint NOT NULL,
    name character varying,
    geom public.geometry(MultiPolygon, 4326) NOT NULL,
    type smallint NOT NULL,
    CONSTRAINT zones_pk PRIMARY KEY (id, type),
    CONSTRAINT zones_type_fkey FOREIGN KEY (type) REFERENCES public.zone_type (id)
);


CREATE INDEX IF NOT EXISTS sidx_zones_geom ON public.zones USING gist (geom);
