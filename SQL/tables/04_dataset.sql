--
-- Name: dataset_id_seq; Type: SEQUENCE; Schema: public
-- (Dedicated sequence for dataset.id; areas use areas_id_seq from road-graph-tool.)
--

CREATE SEQUENCE IF NOT EXISTS public.dataset_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dataset; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.dataset (
    id integer DEFAULT nextval('public.dataset_id_seq'::regclass) NOT NULL,
    name character varying,
    description character varying,
    area integer,
    CONSTRAINT dataset_pk PRIMARY KEY (id)
);
