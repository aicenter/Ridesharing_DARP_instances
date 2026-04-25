--
-- Name: address_block; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.address_block (
    id integer NOT NULL,
    name character varying,
    centroid public.geometry(Point, 4326) NOT NULL,
    CONSTRAINT address_block_pk PRIMARY KEY (id)
);
