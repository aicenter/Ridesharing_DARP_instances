# Instances and Results
**Both the instances and results can be downloaded from [Google Drive](https://drive.google.com/drive/folders/1iTwpQUZdbSC_5kdEb5-eFw2tLPBNnTxh?usp=sharing).** Note that You need a fast connection as the distance matrix files that represents the travel time model are up to 45 GB in size.

## Instance structure

The instances are organized into directories based on their parameters. That is, instance in an *area*, with givben *start time*, *duration* and *max delay* $\Delta$ is in directory.
```text
Instances/<area>/instances/start_<start time>/duration_<duration>/max_delay_<max delay>/
```
Each instance consists of three main files, `vehicles.csv`, `trips.csv` and the distance matrix `dm.hd5`.

### Instance Requests and Vehicles files

Concrete example of an instance path is `Instances/NYC/instances/start_18-00/duration_05_min/max_delay_03_min/`. The instance folder contains the two main instance files:

- 🗎`trips.csv` - a 3 (4) column <tab> separated file containing the list of requests $R$ with header defining following columns:
  - `time_ms` - a request time in miliseconds from the start of the instance $t$
  - `origin` - index of the origin node $o$. Used for indexing into the distance matrix 
  - `dest` - index of the destination node $d$
  - `min_travel_time` (optional) - direct travel time between origin and destination nodes
- 🗎`vehicles.csv` - a 2 column <tab> separated file containing the set of vehicles $V$ with no header row and following column meaning:
  - vehicle starting node $s$ 
  - vehicle capacity $c$

### Distance Matrix - the travel time model
  
The travel time model $f_t(l, l')$ that determines the shortest travel time between any two nodes $l$ and $l'$ has a form of distance matrix and is shared by all instances in the same area. It has a form of distance matrix and is saved in following path:
```text
Instances/<area>/dm.h5
```
Since for some areas the matrix is quite large, it is saved using the `hdf5` format. To load the distance matrix into python, use [`h5py` python package](https://www.h5py.org/). The loading of the distance matrix is implemented in the [`MatrixTravelTimeProvider.from_hdf`](https://github.com/aicenter/Ridesharing_DARP_instances/blob/main/python/darpinstances/instance.py#L62). Method [`get_travel_time(from_index, to_index)`](https://github.com/aicenter/Ridesharing_DARP_instances/blob/main/python/darpinstances/instance.py#L73) implements the acces to the distance matrix and is equivalent to $f_t(l, l')$

## Instance metadata and supporting files
  
In addition to the main instance files, the instance and area folders contain number of additional files holding metadata about the instance used for instance generation, visualization or analysis. List of the files with their location in the directory tree is below. 
  
```text
Instances/
├── NYC/
│   └── ...
├── Manhattan/
│   └── ...
├── DC/
│   └── ...
└── Chicago/
    ├── dm.h5                                                   # Area-specific distance matrix                 
    ├── map/
    │   ├── nodes.csv                                           #           
    │   ├── edges.csv                                           #           
    │   ├── map.xeng                                            #            
    │   └── shapefiles/                                         #
    │       ├── nodes.[shx, shp, prh, dbf, cpg]
    │       └── edges.[shx, shp, prh, dbf, cpg]
    └── instances/
        ├── start_<time>/
        │   ├── duration_<duration>/
        │   │   ├── max_delay_<delay>/
        │   │   │   ├── config.yaml                             # Instance generation config file
        │   │   │   ├── trips.csv                               # 
        │   │   │   ├── vehicles.csv                            #
        │   │   │   ├── trips.di                                # TODO David
        │   │   │   ├── sizing.csv                              # (optional) - file holding data on the instance sizing process
        │   │   │   ├── vehicles_pre_sizing.csv                 # (optional)
        │   │   │   └── shapefiles/                             #
        │   │   │       ├── vehicles.[shx, shp, prh, dbf, cpg] 
        │   │   │       ├── pickup.[shx, shp, prh, dbf, cpg]
        │   │   │       └── dropoff.[shx, shp, prh, dbf, cpg]
        │   │   └── ...
        │   └── ...
        └── ...
```

**Instance configuration files** files:
- 🗎`config.yaml` contains metadata used in the instance generation. Notable fields are 
  - `demand: min_time` and `demand:max_time` that give the interval for the demand used in the instance, 
  - `max_prolongation` - same as maximum delay $\Delta$
  - `vehicles: start_time` - start of the interval for demand used in vehicle location generation 
  - `vehicles: vehicle_capacity` - sets the capacity parameter $c$ for the instance generation
  - `vehicles: vehicle_count` - sets the number of vehicles for the instance generation
- 🗎`sizing.csv` 
  

  
  
  
  

# Instance Creation
## Road Network Processing

## Demand and Vehicle Processing

### Extracting Demand from the Public Datasets

| Area | Demand Dataset | Zone Dataset | Request times |
| --- | --- | --- | --- |
| New York City and Manhattan | [NYC Taxi and Limousine Commission](https://www1.nyc.gov/site/tlc/about/tlc-trip-record-data.page) | [NYC taxi zones]() | exact
| Chicago | [City of Chicago](https://data.cityofchicago.org/Transportation/Taxi-Trips/wrvz-psew) | [Census tracts and community areas]() | generated
| Washington, DC | [City of Washington, DC](https://opendata.dc.gov/search?q=taxi%20trips) | [Master Address Repository]() | generated
