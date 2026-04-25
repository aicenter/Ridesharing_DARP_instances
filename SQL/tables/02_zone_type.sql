--
-- Name: zone level_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE IF NOT EXISTS public."zone level_id_seq"
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_type; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.zone_type (
    id smallint DEFAULT nextval('public."zone level_id_seq"'::regclass) NOT NULL,
    name character varying NOT NULL,
    CONSTRAINT "zone level_pk" PRIMARY KEY (id)
);


CREATE UNIQUE INDEX IF NOT EXISTS "zone level_id_uindex" ON public.zone_type USING btree (id);
