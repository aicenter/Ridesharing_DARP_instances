DARP instances SQL add-on (demand / zones / trips)

Prerequisite: apply the road-graph-tool database schema first: run road-graph-tool/python/scripts/install_sql.py with your config)

Then apply this repository, in order:

  1. `tables/*.sql` — lexicographic order (`01_ … 11_`)
  2. `functions/*.sql`
  3. `procedures/*.sql`

# Procedures

## generate_demand_positions

Samples origin and destination network nodes for selected demand requests and inserts them into `trip_locations`.

Example with an existing location set:

```sql
CALL generate_demand_positions(
    p_area_id => 1,
    p_demand_dataset_ids => ARRAY[2, 3, 4, 5],
    p_trip_location_set_id => 1,
    p_start_time => '2022-03-11 18:00:00',
    p_end_time => '2022-03-11 18:59:59',
    p_zone_types => ARRAY[2]::smallint[],
    p_ignored_zones => ARRAY[1, 264, 265]::bigint[]
);
```

Example creating a new location set:

```sql
CALL generate_demand_positions(
    p_area_id => 1,
    p_demand_dataset_ids => ARRAY[2, 3, 4, 5],
    p_trip_location_set_description => 'NYC Friday evening demand positions',
    p_zone_types => ARRAY[2]::smallint[]
);
```

Validation failures raise exceptions, so the current transaction is aborted and rolled back. Requests whose origin or destination zone is outside the selected area are ignored; neighborhood-zone fallback is checked only against the remaining in-area requests.

# address_block

Column | Type | Required | Description
------- | ------ | ------ | ------------
`id` | integer | Yes | Unique identifier for the address block
`name` | character varying | No | Optional label
`centroid` | geometry(Point, 4326) | Yes | Representative point for the block (WGS 84)


# dataset

Column | Type | Required | Description
------- | ------ | ------ | ------------
`id` | integer | Yes | Unique identifier for the dataset (default from `dataset_id_seq`)
`name` | character varying | No | Name of the dataset
`description` | character varying | No | Description of the dataset
`area` | integer | No | Area identifier


# demand

Column | Type | Required | Description
------- | ------ | ------ | ------------
`id` | integer | Yes | Unique identifier for the trip request (default from `demand_id_seq`)
`origin` | bigint | Yes | Origin node id (`nodes.id` from road-graph-tool)
`destination` | bigint | Yes | Destination node id (`nodes.id` from road-graph-tool)
`origin_time` | timestamp without time zone | Yes | Request start time
`dataset` | integer | Yes | Foreign key to `dataset.id`
`passenger_count` | smallint | No | Number of passengers (default 1)
`destination_time` | timestamp without time zone | No | Request end / arrival time, if known
`source_id` | bigint | No | External source identifier; with `dataset` forms a unique pair when both set



# positions_view (view)

Columns exposed by the view (not a base table). Joins `trip_locations` to `nodes` for origin and destination geometries.

Column | Type | Required | Description
------- | ------ | ------ | ------------
`request_id` | integer | Yes | Demand request id (`demand.id`)
`set` | integer | Yes | Trip location set id (`trip_location_sets.id`)
`origin` | geometry | Yes | Origin node geometry (`nodes.geom`)
`destination` | geometry | Yes | Destination node geometry (`nodes.geom`)

# schema_info

Column | Type | Required | Description
------- | ------ | ------ | ------------
`version` | integer | Yes | Schema or data version key (primary key)

# trip_location_sets

Column | Type | Required | Description
------- | ------ | ------ | ------------
`id` | integer | Yes | Unique identifier for the location set (default from `trip_location_sets_id_seq`)
`description` | character varying | Yes | Human-readable label for this set of alternate OD pairs

# trip_locations

Column | Type | Required | Description
------- | ------ | ------ | ------------
`request_id` | integer | Yes | Foreign key to `demand.id`
`origin` | bigint | Yes | Origin node id (`nodes.id`)
`destination` | bigint | Yes | Destination node id (`nodes.id`)
`set` | integer | Yes | Foreign key to `trip_location_sets.id`; with `request_id` forms the primary key

# trip_time_sets

Column | Type | Required | Description
------- | ------ | ------ | ------------
`id` | integer | Yes | Unique identifier for the time set (default from `trip_time_sets_id_seq`)
`description` | character varying | No | Optional label for this collection of trip times

# trip_times

Column | Type | Required | Description
------- | ------ | ------ | ------------
`request_id` | integer | Yes | Foreign key to `demand.id`; with `set` forms the primary key
`time` | timestamp without time zone | Yes | Sampled or assigned trip time for the request
`set` | integer | Yes | Foreign key to `trip_time_sets.id`

# zone_type

Column | Type | Required | Description
------- | ------ | ------ | ------------
`id` | smallint | Yes | Zone category id (default from `"zone level_id_seq"`)
`name` | character varying | Yes | Category name

# zones

Column | Type | Required | Description
------- | ------ | ------ | ------------
`id` | bigint | Yes | Zone identifier (part of primary key with `type`)
`name` | character varying | No | Optional zone label
`geom` | geometry(MultiPolygon, 4326) | Yes | Zone boundary (WGS 84)
`type` | smallint | Yes | Foreign key to `zone_type.id` (part of primary key with `id`)
