--
-- Name: schema_info; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.schema_info (
    version integer NOT NULL,
    CONSTRAINT pk_schema_info PRIMARY KEY (version)
);
