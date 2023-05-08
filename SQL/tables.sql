create table if not exists public.areas
(
    id          integer default nextval('dataset_id_seq'::regclass) not null
        constraint dataset_pkey
            primary key,
    name        varchar                                             not null,
    description varchar,
    geom        geometry(MultiPolygon)
);

alter table public.areas
    owner to fiedler;

create table if not exists public.spatial_ref_sys
(
    srid      integer not null
        primary key
        constraint spatial_ref_sys_srid_check
            check ((srid > 0) AND (srid <= 998999)),
    auth_name varchar(256),
    auth_srid integer,
    srtext    varchar(2048),
    proj4text varchar(2048)
);

alter table public.spatial_ref_sys
    owner to fiedler;

grant select on public.spatial_ref_sys to public;

create table if not exists public.zone_type
(
    id   smallint default nextval('"zone level_id_seq"'::regclass) not null
        constraint "zone level_pk"
            primary key,
    name varchar                                                   not null
);

alter table public.zone_type
    owner to fiedler;

create table if not exists public.zones
(
    id   bigint                       not null,
    name varchar,
    geom geometry(MultiPolygon, 4326) not null,
    type smallint                     not null
        references public.zone_type,
    constraint zones_pk
        primary key (id, type)
);

alter table public.zones
    owner to fiedler;

create index if not exists sidx_zones_geom
    on public.zones using gist (geom);

create unique index if not exists "zone level_id_uindex"
    on public.zone_type (id);

create table if not exists public.schema_info
(
    version integer not null
        constraint pk_schema_info
            primary key
);

alter table public.schema_info
    owner to fiedler;

create table if not exists public.relations
(
    id   bigint not null
        constraint pk_relations
            primary key,
    tags hstore
);

alter table public.relations
    owner to fiedler;

create table if not exists public.relation_members
(
    relation_id bigint  not null,
    member_id   integer not null,
    member_type text    not null,
    member_role text    not null,
    sequence_id integer not null,
    constraint pk_relation_members
        primary key (relation_id, sequence_id)
);

alter table public.relation_members
    owner to fiedler;

create table if not exists public.dataset
(
    id          integer default nextval('dataset_id_seq'::regclass) not null
        constraint dataset_pk
            primary key,
    name        varchar,
    description varchar,
    area        integer
);

alter table public.dataset
    owner to fiedler;

create table if not exists public.demand
(
    id               serial
        primary key,
    origin           bigint    not null,
    destination      bigint    not null,
    origin_time      timestamp not null,
    dataset          integer   not null
        constraint fk_demand_dataset_1
            references public.dataset,
    passenger_count  smallint default 1,
    destination_time timestamp,
    source_id        bigint,
    constraint demand_source_key
        unique (source_id, dataset)
);

alter table public.demand
    owner to fiedler;

create index if not exists origine_time__index
    on public.demand (origin_time);

create index if not exists dataset__index
    on public.demand (dataset);

create index if not exists demand_destination_index
    on public.demand (destination);

create index if not exists demand_origin_index
    on public.demand (origin);

create index if not exists demand_dataset_origin_index
    on public.demand (dataset, origin);

create index if not exists demand_dataset_destination_index
    on public.demand (dataset, destination);

create table if not exists public.trip_location_sets
(
    id          serial
        primary key,
    description varchar not null
);

alter table public.trip_location_sets
    owner to fiedler;

create table if not exists public.trip_time_sets
(
    id          serial
        primary key,
    description varchar
);

alter table public.trip_time_sets
    owner to fiedler;

create table if not exists public.trip_times
(
    request_id integer   not null
        constraint fk_trip_times_demand_1
            references public.demand,
    time       timestamp not null,
    set        integer   not null
        constraint fk_trip_times_trip_time_sets_1
            references public.trip_time_sets,
    constraint trip_times_pk
        primary key (request_id, set)
);

alter table public.trip_times
    owner to fiedler;

create table if not exists public.address_block
(
    id       integer               not null
        constraint address_block_pk
            primary key,
    name     varchar,
    centroid geometry(Point, 4326) not null
);

alter table public.address_block
    owner to fiedler;

create table if not exists public.nodes_tmp
(
    id     integer default nextval('nodes_id_seq'::regclass) not null
        constraint pk_nodes_tmp
            primary key,
    geom   geometry(Point, 4326),
    osm_id bigint
);

alter table public.nodes_tmp
    owner to fiedler;

create index if not exists nodes_tmp_osm_id_index
    on public.nodes_tmp (osm_id);

create table if not exists public.speed_datasets
(
    id          integer not null
        primary key,
    name        varchar not null,
    description varchar
);

alter table public.speed_datasets
    owner to fiedler;

create table if not exists public.speed_records
(
    datetime    timestamp not null,
    from_osm_id bigint    not null,
    to_osm_id   bigint    not null,
    speed       real      not null,
    st_dev      real,
    dataset     smallint
);

alter table public.speed_records
    owner to fiedler;

create index if not exists speed_records_from_osm_id_to_osm_id_index
    on public.speed_records (from_osm_id, to_osm_id);

create table if not exists public.speeds
(
    way_id        bigint   not null,
    speed_dataset smallint not null
        constraint fk_speeds_speed_datasets_1
            references public.speed_datasets,
    speed         real     not null,
    way_area      integer  not null,
    speed_source  smallint not null,
    primary key (way_id, way_area, speed_dataset)
);

alter table public.speeds
    owner to fiedler;

create table if not exists public.speed_records_quarterly
(
    year        smallint,
    quarter     smallint,
    hour        smallint,
    from_osm_id bigint,
    to_osm_id   bigint,
    speed_mean  double precision,
    st_dev      double precision,
    speed_p50   double precision,
    speed_p85   double precision,
    dataset     smallint
);

alter table public.speed_records_quarterly
    owner to fiedler;

create table if not exists public.nodes
(
    id         bigint                not null
        constraint pk_nodes
            primary key,
    geom       geometry(Point, 4326) not null,
    area       integer               not null
        constraint fk_nodes_areas_1
            references public.areas,
    contracted boolean default false not null
);

comment on column public.nodes.area is 'Area with which was the node imported to the databas';

alter table public.nodes
    owner to fiedler;

create table if not exists public.trip_locations
(
    request_id  integer not null
        constraint fk_trip_locations_demand_1
            references public.demand,
    origin      bigint  not null
        constraint trip_locations_origin_nodes_id_fk
            references public.nodes,
    destination bigint  not null
        constraint trip_locations_destination_nodes_id_fk
            references public.nodes,
    set         integer not null
        constraint fk_trip_locations_trip_location_sets_1
            references public.trip_location_sets,
    constraint trip_locations_pk
        primary key (request_id, set)
);

alter table public.trip_locations
    owner to fiedler;

create index if not exists trip_locations_destination_index
    on public.trip_locations (destination);

create index if not exists trip_locations_origin_index
    on public.trip_locations (origin);

create index if not exists nodes_geom_index
    on public.nodes using gist (geom);

create index if not exists nodes_area_index
    on public.nodes (area);

create table if not exists public.ways
(
    id     bigint                   not null
        constraint pk_ways
            primary key,
    tags   hstore,
    geom   geometry(Geometry, 4326) not null,
    area   integer                  not null
        constraint ways_areas_id_fk
            references public.areas,
    "from" bigint                   not null
        constraint ways_from_nodes_id_fk
            references public.nodes,
    "to"   bigint                   not null
        constraint ways_to_nodes_id_fk
            references public.nodes,
    oneway boolean                  not null
);

alter table public.ways
    owner to fiedler;

create index if not exists geom__index
    on public.ways using gist (geom);

create index if not exists ways_from_index
    on public.ways ("from");

create index if not exists ways_to_index
    on public.ways ("to");

create table if not exists public.edges
(
    "from" bigint
        constraint edges_nodes_id_fk
            references public.nodes,
    "to"   bigint
        constraint edges_nodes_id_fk2
            references public.nodes,
    id     integer default nextval('edge_id_seq'::regclass) not null
        constraint edges_pk
            primary key,
    geom   geometry(MultiLineString)                        not null,
    area   smallint                                         not null
        constraint edges_areas_id_fk
            references public.areas,
    speed  double precision                                 not null
);

comment on column public.edges.area is 'The are for which the edge was generated using the simplification/contraction procedure';

alter table public.edges
    owner to fiedler;

create index if not exists edges_geom_index
    on public.edges using gist (geom);

create index if not exists edges_from_to_index
    on public.edges ("from", "to");

create index if not exists edges_from_index
    on public.edges ("from");

create index if not exists edges_to_index
    on public.edges ("to");

create table if not exists public.speed_record_datasets
(
    id          smallint,
    name        varchar,
    description varchar
);

alter table public.speed_record_datasets
    owner to fiedler;

create table if not exists public.nodes_ways
(
    way_id   integer  not null
        constraint nodes_ways_ways_id_fk
            references public.ways,
    node_id  bigint   not null
        constraint nodes_ways_nodes_id_fk
            references public.nodes,
    position smallint not null,
    area     smallint not null
        constraint nodes_ways_areas_id_fk
            references public.areas,
    id       serial
        constraint nodes_ways_pk
            primary key,
    constraint nodes_ways_unique_way_position
        unique (way_id, position)
);

alter table public.nodes_ways
    owner to fiedler;

create index if not exists nodes_ways_node_id_index
    on public.nodes_ways (node_id);

create index if not exists nodes_ways_way_id_index
    on public.nodes_ways (way_id);

create table if not exists public.nodes_ways_tmp
(
    way_id   integer  not null,
    node_id  integer  not null,
    position smallint not null
);

alter table public.nodes_ways_tmp
    owner to fiedler;

create table if not exists public.ways_tmp
(
    id     bigint                   not null
        constraint pk_ways_tmp
            primary key,
    tags   hstore,
    geom   geometry(Geometry, 4326) not null,
    "from" integer                  not null,
    "to"   integer                  not null,
    osm_id bigint                   not null,
    oneway boolean                  not null
);

alter table public.ways_tmp
    owner to fiedler;

create table if not exists public.nodes_edges
(
    node_id integer not null,
    edge_id integer not null
);

alter table public.nodes_edges
    owner to fiedler;

create table if not exists public.nodes_ways_speeds
(
    from_node_ways_id    integer          not null
        constraint nodes_ways_speeds_nodes_ways_id_fk
            references public.nodes_ways,
    speed                double precision not null,
    st_dev               double precision not null,
    to_node_ways_id      integer          not null
        constraint nodes_ways_speeds_nodes_ways_id_fk2
            references public.nodes_ways,
    quality              smallint,
    source_records_count integer,
    constraint nodes_ways_speed_records_pk
        primary key (from_node_ways_id, to_node_ways_id)
);

alter table public.nodes_ways_speeds
    owner to fiedler;

create index if not exists nodes_ways_speeds_from_node_ways_id_index
    on public.nodes_ways_speeds (from_node_ways_id);

create index if not exists nodes_ways_speeds_to_node_ways_id_index
    on public.nodes_ways_speeds (to_node_ways_id);

create table if not exists public.component_data
(
    component_id smallint not null,
    node_id      bigint   not null
        constraint component_data_nodes_id_fk
            references public.nodes,
    area         smallint not null,
    constraint component_data_pk
        primary key (node_id, area)
);

comment on column public.component_data.component_id is 'ID of the component, ordered from the largests components, starting from 0';

comment on column public.component_data.area is 'The area for which this component record belongs. Note that one node can be part of the largest component in one area while a part of a small one in some other area ';

alter table public.component_data
    owner to fiedler;

create index if not exists component_data_node_id_component_id_index
    on public.component_data (node_id, component_id);

create index if not exists component_data_node_id_index
    on public.component_data (node_id);

