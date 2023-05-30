# Instances and Results
**Both the instances and results can be downloaded from [Google Drive](https://drive.google.com/drive/folders/1iTwpQUZdbSC_5kdEb5-eFw2tLPBNnTxh?usp=sharing).** Note that You need a fast connection as the distance matrix files that represents the travel time model are up to 45 GB in size.

## Instance structure

The instances are organized into directories based on their parameters. That is, an instance in an *area*, with a given *_start time_*, *duration* and *max delay* $\Delta$ is in the following directory structure:

```text
📁 Instances/<area>/
├── 🗎 dm.hd5
└── 📁instances/start_<start time>/duration_<duration>/max_delay_<max delay>/
    ├── 🗎 vehicles.csv
    └── 🗎 trips.csv
```
and consists of three files, `vehicles.csv`, `trips.csv` and `dm.h5`. The `vehicles.csv` and `trips.csv` files are the main instance files, while the `dm.h5` file is the distance matrix file that represents the travel time model $f_t(l, l')$ used in the instance. The instance files are described in detail below.

### Instance Requests and Vehicles files

The instance folder contains the two main instance files:

`📁Instances/<area>/instances/start_<start time>/duration_<duration>/max_delay_<max delay>/`

- `🗎 trips.csv` - a 3 (4) column `<tab>` separated file containing the list of requests $R$ with a header defining the following columns:
  - `time_ms` - a request time in milliseconds from the start of the instance $t$
  - `origin` - index of the origin node $o$. Used for indexing into the distance matrix 
  - `dest` - index of the destination node $d$
  - `min_travel_time` (optional) - direct travel time between origin and destination nodes
- `🗎 vehicles.csv` - a 2-column `<tab>` separated file containing the set of vehicles $V$ with no header row and the following column meaning:
  - vehicle starting node $s$ 
  - vehicle capacity $c$

A concrete example of an instance path is `Instances/NYC/instances/start_18-00/duration_05_min/max_delay_03_min/`.

### Distance Matrix - the travel time model

`🗎 Instances/<area>/dm.hd5`
  
The travel time model $f_t(l, l')$ that determines the shortest travel time between any two nodes $l$ and $l'$ has a form of distance matrix and is shared by all instances in the same area. 
Since for some areas the matrix is quite large, it is saved using the `hdf5` format. To load the distance matrix into Python, use [`h5py` python package](https://www.h5py.org/). The loading of the distance matrix is implemented in the [`MatrixTravelTimeProvider.from_hdf`](https://github.com/aicenter/Ridesharing_DARP_instances/blob/main/python/darpinstances/instance.py#L62). Method [`get_travel_time(from_index, to_index)`](https://github.com/aicenter/Ridesharing_DARP_instances/blob/main/python/darpinstances/instance.py#L73) implements the access to the distance matrix and is equivalent to $f_t(l, l')$

## Instance metadata and supporting files
  
In addition to the main instance files, the instance and area folders contain several additional files holding metadata about the instance used for instance generation, visualization or analysis. The list of the files with their location in the directory tree is below. 
  
```text
📁Instances/
├── 📁NYC/
│   └── ...
├── 📁Manhattan/
│   └── ...
├── 📁DC/
│   └── ...
└── 📁Chicago/
    ├── 🗎 dm.h5                              # Area-specific distance matrix                 
    ├── 📁map/
    │   ├── 🖺 nodes.csv                      # List of nodes present in the area          
    │   ├── 🖺 edges.csv                      # List of edges present in the area
    │   ├── 🗺 map.xeng                       # TODO David         
    │   └── 📁shapefiles/                    # Area shapefiles for visualization
    │       ├── 🗺 nodes.[shx, shp, prh, dbf, cpg]
    │       └── 🗺 edges.[shx, shp, prh, dbf, cpg]
    └── 📁instances/
        ├── 📁start_<time>/
        │   ├── 📁duration_<duration>/
        │   │   ├── 📁max_delay_<delay>/
        │   │   │   ├── 🖺 config.yaml        # Instance generation config file
        │   │   │   ├── 🗎 trips.csv          # Requests file
        │   │   │   ├── 🗎 vehicles.csv       # Vehicles file
        │   │   │   ├── 🖺 trips.di           # Temporary file used by some solvers, to be removed
        │   │   │   ├── 🖺 sizing.csv         # (optional) - file holding data on the instance sizing process
        │   │   │   ├── 🖺 vehicles_pre_sizing.csv    # (optional) - file holding data on the vehicles before the sizing process
        │   │   │   └── 📁shapefiles/        # Instance shapefiles for visualization
        │   │   │       ├── 🗺 vehicles.[shx, shp, prh, dbf, cpg] 
        │   │   │       ├── 🗺 pickup.[shx, shp, prh, dbf, cpg]
        │   │   │       └── 🗺 dropoff.[shx, shp, prh, dbf, cpg]
        │   │   └── ...
        │   └── ...
        └── ...
```

### Instance generation config files

`📁 Instances/<area>/instances/start_<start time>/duration_<duration>/max_delay_<max delay>/`

- `🖺 config.yaml` contains metadata used in the instance generation. Notable fields are 
  - `demand: min_time` and `demand:max_time` that give the interval for the demand used in the instance, 
  - `max_prolongation` - same as maximum delay $\Delta$
  - `vehicles: `start_time` - the start of the interval for demand used in vehicle location generation 
  - `vehicles: vehicle_capacity` - sets the capacity parameter $c$ for the instance generation
  - `vehicles: vehicle_count` - sets the number of vehicles for the instance generation
- `🖺 sizing.csv` contains the results of the instance sizing, step in the instance generation process that selects the number of vehicles for the instance so that solution found by the insertion heuristic can service all requests in the instance. See the article for details. The file uses a comma as a separator and contains three columns with a header:
  - `vehicle_count` - the number of vehicles used at a given step of the sizing process
  - `dropped_requests` - the number of requests that cannot be serviced by the given number of vehicles when solved by the insertion heuristic
  - `interval_size` - the size of the interval-halving step used in the sizing process

`📁 Instances/<area>/map/`
- `🖺 nodes.csv` contains information about processed road network nodes in the area. The file uses `<tab>` as a separator and contains four columns with a header:
  - `id` - node id TODO David - rozdil mezi idecky a ktere je v DB?
  - `db_id` - node id in the database TODO David
  - `x` - node x coordinate TODO David - co je to za projekci?
  - `y` - node y coordinate TODO David - co je to za projekci?
- `🖺 edges.csv` contains information about processed road network edges in the area, including the speed. The file uses `<tab>` as a separator and contains six columns with a header:
  - `u` - from node `id`
  - `v` - to node `id`
  - `db_id_from` - from node `db_id`
  - `db_id_to` - to node `db_id` 
  - `length` - length of the edge in TODO David - jednotky?
  - `speed` - speed of the edge used in travel time calculations, in TODO David - jednotky?

### Visualization files

Contains area and instance files for visuzalization in e.g. [Q-GIS](https://www.qgis.org)

`📁 Instances/<area>/map/`
- `🗺 map.xeng`
- 📁shapefiles/
 - `🗺 nodes.[shx, shp, prh, dbf, cpg]`
 - `🗺 edges.[shx, shp, prh, dbf, cpg]`

`📁 Instances/<area>/instances/start_<start time>/duration_<duration>/max_delay_<max delay>/shapefiles/` 
- `🗺 vehicles.[shx, shp, prh, dbf, cpg]` - starting vehicle locations
- `🗺 pickup.[shx, shp, prh, dbf, cpg]` - request pickup points
- `🗺 dropoff.[shx, shp, prh, dbf, cpg]` - request dropoff points

# Instance Creation
## Road Network Processing

## Demand and Vehicle Processing

### Extracting Demand from the Public Datasets

| Area | Demand Dataset | Zone Dataset | Request times |
| --- | --- | --- | --- |
| New York City and Manhattan | [NYC Taxi and Limousine Commission](https://www1.nyc.gov/site/tlc/about/tlc-trip-record-data.page) | [NYC taxi zones]() | exact
| Chicago | [City of Chicago](https://data.cityofchicago.org/Transportation/Taxi-Trips/wrvz-psew) | [Census tracts and community areas]() | generated
| Washington, DC | [City of Washington, DC](https://opendata.dc.gov/search?q=taxi%20trips) | [Master Address Repository]() | generated
