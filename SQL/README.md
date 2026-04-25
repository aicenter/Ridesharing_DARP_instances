DARP instances SQL add-on (demand / zones / trips)

Prerequisite: apply the road-graph-tool database schema first: run road-graph-tool/python/scripts/install_sql.py with your config)

Then apply this repository, in order:

  1. tables/*.sql   — lexicographic order (01_ … 11_)
  2. functions/*.sql
  3. procedures/*.sql

# address_block

Column | Type | Description
------- | ------ | ------------
`id` | integer | Unique identifier for the address block
`name` | character varying | Optional label
`centroid` | geometry(Point, 4326) | Representative point for the block (WGS 84)

# demand

Column | Type | Description
------- | ------ | ------------
`id` | integer | Unique identifier for the trip request (default from `demand_id_seq`)
`origin` | bigint | Origin node id (`nodes.id` from road-graph-tool)
`destination` | bigint | Destination node id (`nodes.id` from road-graph-tool)
`origin_time` | timestamp without time zone | Request start time
`dataset` | integer | Foreign key to `dataset.id`
`passenger_count` | smallint | Number of passengers (default 1)
`destination_time` | timestamp without time zone | Request end / arrival time, if known
`source_id` | bigint | External source identifier; with `dataset` forms a unique pair when both set

# dataset

Column | Type | Description
------- | ------ | ------------
`id` | integer | Unique identifier for the dataset (default from `dataset_id_seq`)
`name` | character varying | Name of the dataset
`description` | character varying | Description of the dataset
`area` | integer | Area identifier

# positions_view (view)

Columns exposed by the view (not a base table). Joins `trip_locations` to `nodes` for origin and destination geometries.

Column | Type | Description
------- | ------ | ------------
`request_id` | integer | Demand request id (`demand.id`)
`set` | integer | Trip location set id (`trip_location_sets.id`)
`origin` | geometry | Origin node geometry (`nodes.geom`)
`destination` | geometry | Destination node geometry (`nodes.geom`)

# schema_info

Column | Type | Description
------- | ------ | ------------
`version` | integer | Schema or data version key (primary key)

# trip_location_sets

Column | Type | Description
------- | ------ | ------------
`id` | integer | Unique identifier for the location set (default from `trip_location_sets_id_seq`)
`description` | character varying | Human-readable label for this set of alternate OD pairs

# trip_locations

Column | Type | Description
------- | ------ | ------------
`request_id` | integer | Foreign key to `demand.id`
`origin` | bigint | Origin node id (`nodes.id`)
`destination` | bigint | Destination node id (`nodes.id`)
`set` | integer | Foreign key to `trip_location_sets.id`; with `request_id` forms the primary key

# trip_time_sets

Column | Type | Description
------- | ------ | ------------
`id` | integer | Unique identifier for the time set (default from `trip_time_sets_id_seq`)
`description` | character varying | Optional label for this collection of trip times

# trip_times

Column | Type | Description
------- | ------ | ------------
`request_id` | integer | Foreign key to `demand.id`; with `set` forms the primary key
`time` | timestamp without time zone | Sampled or assigned trip time for the request
`set` | integer | Foreign key to `trip_time_sets.id`

# zone_type

Column | Type | Description
------- | ------ | ------------
`id` | smallint | Zone category id (default from `"zone level_id_seq"`)
`name` | character varying | Category name

# zones

Column | Type | Description
------- | ------ | ------------
`id` | bigint | Zone identifier (part of primary key with `type`)
`name` | character varying | Optional zone label
`geom` | geometry(MultiPolygon, 4326) | Zone boundary (WGS 84)
`type` | smallint | Foreign key to `zone_type.id` (part of primary key with `id`)

