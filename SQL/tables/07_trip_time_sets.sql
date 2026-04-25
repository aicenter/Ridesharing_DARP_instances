--
-- Name: trip_time_sets; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.trip_time_sets (
    id integer NOT NULL,
    description character varying,
    CONSTRAINT trip_time_sets_pkey PRIMARY KEY (id)
);


CREATE SEQUENCE IF NOT EXISTS public.trip_time_sets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ONLY public.trip_time_sets ALTER COLUMN id SET DEFAULT nextval('public.trip_time_sets_id_seq'::regclass);
