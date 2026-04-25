--
-- Name: demand; Type: TABLE; Schema: public
--

CREATE TABLE IF NOT EXISTS public.demand (
    id integer NOT NULL,
    origin bigint NOT NULL,
    destination bigint NOT NULL,
    origin_time timestamp without time zone NOT NULL,
    dataset integer NOT NULL,
    passenger_count smallint DEFAULT 1,
    destination_time timestamp without time zone,
    source_id bigint,
    CONSTRAINT demand_pkey PRIMARY KEY (id),
    CONSTRAINT demand_source_key UNIQUE (source_id, dataset),
    CONSTRAINT fk_demand_dataset_1 FOREIGN KEY (dataset) REFERENCES public.dataset (id)
);


CREATE SEQUENCE IF NOT EXISTS public.demand_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ONLY public.demand ALTER COLUMN id SET DEFAULT nextval('public.demand_id_seq'::regclass);


CREATE INDEX IF NOT EXISTS origine_time__index ON public.demand USING btree (origin_time);
CREATE INDEX IF NOT EXISTS dataset__index ON public.demand USING btree (dataset);
CREATE INDEX IF NOT EXISTS demand_destination_index ON public.demand USING btree (destination);
CREATE INDEX IF NOT EXISTS demand_origin_index ON public.demand USING btree (origin);
CREATE INDEX IF NOT EXISTS demand_dataset_origin_index ON public.demand USING btree (dataset, origin);
CREATE INDEX IF NOT EXISTS demand_dataset_destination_index ON public.demand USING btree (dataset, destination);
