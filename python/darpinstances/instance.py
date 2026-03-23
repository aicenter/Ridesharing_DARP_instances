# from __future__ import annotations
import logging
import math
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, time, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Dict, List, Optional, Sequence, TextIO, Tuple, Union

import geojson
import numpy as np
import pandas as pd
import yaml
from pyproj import Transformer
from scipy.spatial import KDTree
from tqdm.autonotebook import tqdm

import darpinstances.log
from darpinstances.inout import check_file_exists
from darpinstances.instance_objects import Coordinate, Request, Vehicle
from darpinstances.utils import TimeLoader, DarpinstancesTimestampLoader
from darpinstances.travel_time_provider import (
    TravelTimeProvider,
    EuclideanTravelTimeProvider,
    MatrixTravelTimeProvider,
    GridTravelTimeProvider,
)


class DARPInstanceConfiguration:
    def __init__(
        self,
        max_route_duration: int,
        max_ride_time: int,
        return_to_depot: bool = True,
        virtual_vehicles: bool = False,
        start_time: datetime = datetime.fromtimestamp(0, tz=timezone.utc),
        min_pause_length: int = 0,
        max_pause_interval: int = 0,
        travel_time_divider: int = 1,
        max_pickup_delay: int = 0,
        enable_negative_delay: bool = False,
        vehicle_capacity: Optional[int] = None,
        vehicle_capital_cost: Optional[float] = None,
        relative_delay_cost: float = 0,
        problem: str = "DARP",
    ):
        self.max_route_duration = max_route_duration
        self.max_ride_time = max_ride_time
        self.return_to_depot = return_to_depot
        self.virtual_vehicles = virtual_vehicles
        self.start_time = start_time
        self.min_pause_length = min_pause_length
        self.max_pause_interval = max_pause_interval
        self.travel_time_divider = travel_time_divider
        self.max_pickup_delay = max_pickup_delay
        self.enable_negative_delay = enable_negative_delay
        self.vehicle_capacity = vehicle_capacity
        self.vehicle_capital_cost = vehicle_capital_cost
        self.relative_delay_cost = relative_delay_cost
        self.problem = problem

    @property
    def is_fleet_sizing(self) -> bool:
        return self.problem.lower() == "fleet-sizing"


class DARPInstance:

    def __init__(
        self,
        requests: Iterable[Request],
        vehicles: Sequence[Vehicle],
        travel_time_provider: TravelTimeProvider,
        darp_instance_config: DARPInstanceConfiguration
    ):
        self.requests = requests
        self.vehicles: Sequence[Vehicle] = vehicles
        self.travel_time_provider = travel_time_provider
        self.darp_instance_config = darp_instance_config
        self.request_map = {r.index: r for r in requests}


class Reader(ABC):

    @abstractmethod
    def read(self, filepath: str) -> DARPInstance:
        pass


def _set_config_defaults(config: Dict, defaults: Dict):
    for key, val in defaults.items():
        if isinstance(val, dict):
            _set_config_defaults(config[key], defaults[key])
        else:
            if key not in config:
                config[key] = defaults[key]


def load_instance_config(config_file_path: Path, set_defaults: bool = True) -> dict:
    config_file_path_abs = config_file_path.absolute()
    logging.info(f"Loading instance config from {config_file_path_abs}")
    with open(config_file_path_abs, 'r') as config_file:
        config = yaml.load(config_file, Loader=DarpinstancesTimestampLoader)

        if set_defaults:
            defaults = {
                'instance_dir': os.path.dirname(config_file_path),
                'map': {'path': config_file_path.parent / 'map'},
                'demand': {'type': 'generate', 'min_time': 0, 'max_time': 86_400  # 24:00
                },
                'vehicles': {'start_time': config['demand']['min_time']}}

            _set_config_defaults(config, defaults)
        return config


def instance_problem_from_config(instance_config: Dict) -> str:
    raw = instance_config.get("problem", "DARP")
    if raw is None:
        return "DARP"
    s = str(raw).strip()
    return s if s else "DARP"


def instance_config_indicates_fleet_sizing(instance_config: Dict) -> bool:
    return instance_problem_from_config(instance_config).lower() == "fleet-sizing"


def load_vehicles_csv(vehicles_path: Path) -> List[Vehicle]:
    veh_data = darpinstances.inout.load_csv(vehicles_path, "\t")
    vehicles = []
    for index, veh in enumerate(veh_data):
        vehicles.append(Vehicle(index, int(veh[0]), int(veh[1])))

    return vehicles


class EquipmentType(Enum):
    NONE = 0
    STANDARD_SEAT = 1
    WHEELCHAIR = 2
    ELECTRIC_WHEELCHAIR = 3
    SPECIAL_NEEDS_STROLLER = 4


def map_equipment_type(equipment_str: str) -> EquipmentType:
    equipment_mapping = {
        "NONE": EquipmentType.NONE,
        "STANDARD_SEAT": EquipmentType.STANDARD_SEAT,
        "WHEELCHAIR": EquipmentType.WHEELCHAIR,
        "ELECTRIC_WHEELCHAIR": EquipmentType.ELECTRIC_WHEELCHAIR,
        "SPECIAL_NEEDS_STROLLER": EquipmentType.SPECIAL_NEEDS_STROLLER, }
    return equipment_mapping.get(equipment_str, EquipmentType.NONE)


def _load_datetime(string: str):
    return datetime.strptime(string, '%Y-%m-%d %H:%M:%S')


def load_vehicles_from_json(vehicles_path: Path, stations_path: Path) -> List[Vehicle]:
    veh_data = darpinstances.inout.load_json(vehicles_path)
    station_data = darpinstances.inout.load_csv(stations_path, "\t")
    stations = []
    for index, station in enumerate(station_data):
        stations.append(int(station[0]))
    vehicles = []
    for index, veh in enumerate(veh_data):
        configurations = []
        if "slots" in veh:
            equipment = []
            for item in veh["slots"]:
                count = int(item["count"])
                equipment_type = map_equipment_type(item["type"])
                for n in range(count):
                    equipment.append(equipment_type.value)
            configurations.append(equipment)
        elif "configurations" in veh:
            equipment_list = [equipment.name for equipment in EquipmentType]
            for item in veh["configurations"]:
                configuration_equipment = []
                for equipment_name in equipment_list:
                    equipment_type = map_equipment_type(equipment_name)
                    count = int(item.get(equipment_name, 0))
                    for i in range(count):
                        configuration_equipment.append(equipment_type.value)
                configurations.append(configuration_equipment)
        config_capacities = [len(config) for config in configurations]
        max_capacity = max(config_capacities) if config_capacities else 0
        capacity = veh["capacity"] if "capacity" in veh else max_capacity
        operation_start = _load_datetime(veh["operation_start"]) if "operation_start" in veh else None
        operation_end = _load_datetime(veh["operation_end"]) if "operation_end" in veh else None
        initial_position = stations[int(veh["station_index"])]
        vehicles.append(
            Vehicle(int(veh["id"]), initial_position, capacity, configurations, operation_start, operation_end)
        )

    return vehicles


def load_vehicles(instance_dir_path: Path, instance_config: Dict) -> List[Vehicle]:
    # one option is to not define vehicles at all and let the system generate them at the pickup loactions
    if ('vehicles' in instance_config and 'origin' in instance_config['vehicles'] and instance_config['vehicles'][
        'origin'] == 'on-demand'):
        return []

    vehicles_path_csv = instance_dir_path / 'vehicles.csv'
    vehicles_path_json = instance_dir_path / 'vehicles.json'
    if 'vehicles' in instance_config and 'filepath' in instance_config['vehicles']:
        vehicles_path_json = instance_dir_path / instance_config['vehicles']['filepath']

    stations_path_csv = instance_dir_path / 'station_positions.csv'
    csv_exists = check_file_exists(vehicles_path_csv, raise_ex=False)
    json_exists = check_file_exists(vehicles_path_json, raise_ex=False)
    stations_csv_exists = check_file_exists(vehicles_path_json, raise_ex=False)

    if json_exists and stations_csv_exists:
        return load_vehicles_from_json(vehicles_path_json, stations_path_csv)
    elif csv_exists:
        return load_vehicles_csv(vehicles_path_csv)
    else:
        raise ValueError("Vehicles file .json or .csv was not found")


def _compute_max_delay(instance_config: dict, min_travel_time: int|float) -> float:
    if 'max_prolongation' in instance_config:
        return int(instance_config['max_prolongation'])
    elif instance_config['max_travel_time_delay']['mode'] == 'absolute':
        return instance_config['max_travel_time_delay']['seconds']
    else:
        return min_travel_time * instance_config['max_travel_time_delay']['relative']


def load_demand_legacy(
    demand_file: TextIO,
    instance_config: dict,
    travel_time_provider: TravelTimeProvider,
    demand_file_path: Path,
    time_loader: TimeLoader
):
    """
    Old loader for demand files in the format present in the original DARP instances requests.csv files. This loader
    should not be needed any more, as the new loader is more flexible, but it kept here for possible compatibility
    issues with old instances. It is used only for the old space-separated format files.

    @param demand_file: file object
    @param requests: list of requests to be filled
    @param instance_config: instance configuration
    @param travel_time_provider: travel time provider
    """
    action_id = 0
    index = 0
    travel_time_divider = instance_config.get('travel_time_divider', 1)

    if demand_file_path.suffix == '.di':
        column_indices = {'time': 1, 'origin': 2, 'destination': 3}
    else:
        # skip header
        demand_file.readline()
        column_indices = {'time': 0, 'origin': 1, 'destination': 2}
    time_column = column_indices['time']

    line_string = demand_file.readline()
    requests = []
    while line_string:
        line = line_string.split()
        request_id: int = int(index)

        request_datetime = time_loader.load_time_field(int(line[time_column]) / 1000)

        start_node = int(line[column_indices['origin']])
        end_node = int(line[column_indices['destination']])
        equipment = map_equipment_type(line[4]).value if (len(line) > 4) else 0

        min_travel_time = travel_time_provider.get_travel_time(start_node, end_node)
        min_travel_time = min_travel_time / travel_time_divider

        max_prolongation = _compute_max_delay(instance_config, min_travel_time)
        max_pickup_delay = instance_config.get('max_pickup_delay', max_prolongation)

        max_pickup_time = request_datetime + timedelta(seconds=max_pickup_delay)
        # min_drop_off_time = request_time + timedelta(seconds=int(min_travel_time))
        max_drop_off_time = request_datetime + timedelta(seconds=int(min_travel_time)) + timedelta(
            seconds=max_prolongation
        ) + timedelta(seconds=instance_config.get('max_pickup_delay', 0))
        if 'max_pickup_delay' in instance_config:
            max_drop_off_time += timedelta(seconds=instance_config['max_pickup_delay'])

        vehicle_id = int(line[5]) if len(line) > 5 else None
        requests.append(
            Request(
                request_id,
                action_id,
                start_node,
                request_datetime,
                max_pickup_time,
                action_id + 1,
                end_node,
                # min_drop_off_time,
                max_drop_off_time,
                math.ceil(min_travel_time),
                0,
                0,
                equipment,
                vehicle_id
            )
        )
        line_string = demand_file.readline()
        action_id += 2
        index += 1

    return requests


def _compute_min_pickup_time(instance_config: dict, desired_pickup_time: datetime) -> datetime:
    if 'enable_negative_delay' in instance_config and instance_config['enable_negative_delay']:
        min_time_including_negative_delay = desired_pickup_time - timedelta(seconds=instance_config['max_pickup_delay'])
        if 'min_time' in instance_config['demand']:
            instance_start_time = _load_datetime(instance_config['demand']['min_time'])
            if instance_start_time > min_time_including_negative_delay:
                return instance_start_time
        return min_time_including_negative_delay
    return desired_pickup_time


def get_nearest_node(kdtree: KDTree, transformer: Transformer, latitude: str, longitude: str) -> int:
    transformed_coords = transformer.transform(float(longitude), float(latitude))
    return int(kdtree.query([transformed_coords[0], transformed_coords[1]])[1])


# def _load_request(row: pd.DataFrame) -> Request:
#     return Request(
#         row['id'],
#         action_id,
#         start_node,
#         min_pickup_time,
#         max_pickup_time,
#         action_id + 1,
#         end_node,
#         max_drop_off_time,
#         math.ceil(min_travel_time),
#         0,
#         0,
#         equipment,
#         vehicle_id
#     )


def load_demand(demand_file: TextIO, instance_config: dict, travel_time_provider: TravelTimeProvider, time_loader: TimeLoader):
    """
    Function that loads requests from a csv file.

    @param demand_file: file object
    @param requests: list of requests to be filled
    @param instance_config: instance configuration
    @param travel_time_provider: travel time provider
    """

    # the presence of the SRID signals that the graph nodes for requests' origin and destination are not precomputed
    if 'srid' in instance_config:
        # Create a transformer object
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{instance_config['srid']}", always_xy=True)

        # read the nodes
        input_stream = open(Path(instance_config['area_dir']) / 'maps/nodes.geojson', encoding='utf8')
        geojson_nodes = geojson.load(input_stream)
        coord_list = []
        for node in tqdm(geojson_nodes['features']):
            coords = node['geometry']['coordinates']

            # transform coordinates to UTM
            coords = transformer.transform(coords[0], coords[1])

            coord_list.append(coords)
        kdtree = KDTree(coord_list)

    travel_time_divider = instance_config.get('travel_time_divider', 1)

    request_data = pd.read_csv(demand_file)

    # convert pickup time to datetime
    request_data['time'] = [time_loader.load_time_field(time) for time in request_data['time']]

    # request id
    if not 'id' in request_data.columns:
        request_data['id'] = request_data.index

    # min pickup time
    request_data['min_pickup_time'] = [_compute_min_pickup_time(instance_config, desired_pickup_time) for
        desired_pickup_time in request_data['time']]

    # nodes
    if 'srid' in instance_config:
        request_data['start_node'] = [get_nearest_node(kdtree, transformer, lat, lon) for lat, lon in
            zip(request_data['Latitude_From'], request_data['Longitude_From'])]
        request_data['end_node'] = [get_nearest_node(kdtree, transformer, lat, lon) for lat, lon in
            zip(request_data['Latitude_To'], request_data['Longitude_To'])]
    else:
        request_data.rename(columns={'origin': 'start_node', 'destination': 'end_node'}, inplace=True)

    # equipment
    if 'Slot_Type' in request_data.columns:
        request_data['equipment'] = [map_equipment_type(slot_type).value for slot_type in request_data['Slot_Type']]
    else:
        request_data['equipment'] = 0

    # minimum travel time from start to end node
    request_data['min_travel_time'] = [travel_time_provider.get_travel_time(start_node, end_node) / travel_time_divider
        for start_node, end_node in zip(request_data['start_node'], request_data['end_node'])]

    # max time computations
    request_data['max_delay'] = [_compute_max_delay(instance_config, min_travel_time) for min_travel_time in
        request_data['min_travel_time']]
    if 'max_pickup_delay' in instance_config:
        request_data['max_pickup_delay'] = instance_config['max_pickup_delay']
    else:
        request_data['max_pickup_delay'] = request_data['max_delay']

    request_data['max_pickup_time'] = request_data['time'] + pd.to_timedelta(request_data['max_pickup_delay'], unit='s')

    request_data['max_drop_off_time'] = request_data['time'] + pd.to_timedelta(
        (request_data['min_travel_time'] + request_data['max_delay'] + instance_config.get('max_pickup_delay', 0)).round(),
        unit='s'
    )

    # required vehicle id, if not present, set to -1
    if 'required_vehicle_id' not in request_data:
        request_data['required_vehicle_id'] = None

    # action ids
    request_data['pickup_action_id'] = request_data.index * 2
    request_data['drop_off_action_id'] = request_data.index * 2 + 1

    # travel time rounding
    request_data['min_travel_time'] = request_data['min_travel_time'].apply(np.ceil)

    return [
        Request(
            request_id,
            pickup_action_id,
            start_node,
            min_pickup_time,
            max_pickup_time,
            drop_off_action_id,
            end_node,
            max_drop_off_time,
            math.ceil(min_travel_time),
            0,
            0,
            equipment,
            required_vehicle_id
        ) for
            request_id,
            pickup_action_id,
            start_node,
            min_pickup_time,
            max_pickup_time,
            drop_off_action_id,
            end_node,
            max_drop_off_time,
            min_travel_time,
            equipment,
            required_vehicle_id
        in zip(
            request_data['id'],
            request_data['pickup_action_id'],
            request_data['start_node'],
            request_data['min_pickup_time'],
            request_data['max_pickup_time'],
            request_data['drop_off_action_id'],
            request_data['end_node'],
            request_data['max_drop_off_time'],
            request_data['min_travel_time'],
            request_data['equipment'],
            request_data['required_vehicle_id']
        )
    ]


def load_instance(
    filepath: Path,
    travel_time_provider: MatrixTravelTimeProvider = None,
    demand_file_name: Optional[str] = None,
    fleet_sizing: bool = False,
) -> Tuple[DARPInstance, TimeLoader]:
    instance_config = load_instance_config(filepath, set_defaults=False)
    instance_dir_path = filepath.parent

    effective_fleet_sizing = fleet_sizing or instance_config_indicates_fleet_sizing(instance_config)

    # Here, we are completing the possibly relative paths. Therefore, we need to change the dir because dm path
    # loaded from instance config is relative to the instance dir
    os.chdir(instance_dir_path)
    if demand_file_name is None:
        demand_path = Path(instance_config['demand']['filepath'])
    else:
        demand_path = instance_dir_path / demand_file_name
    check_file_exists(demand_path)

    vehicles = (
        load_vehicles(instance_dir_path, instance_config) if not effective_fleet_sizing else []
    )

    # dm loading
    if travel_time_provider is None:
        if instance_config.get('type') == 'grid':
            size = instance_config['size']
            distance = instance_config['distance']
            travel_time_provider = GridTravelTimeProvider(size, distance)
            logging.info("Using grid travel time provider (size=%s, distance=%s)", size, distance)
        else:
            if 'dm_filepath' in instance_config:
                dm_filepath = instance_config['dm_filepath']
            else:
                dm_filepath = Path(instance_config['area_dir']) / 'dm.h5'
                if not dm_filepath.exists():
                    dm_filepath = Path(instance_config['area_dir']) / 'dm.csv'
            check_file_exists(dm_filepath)
            logging.info("Reading dm from: {}".format(os.path.realpath(dm_filepath)))
            travel_time_provider = MatrixTravelTimeProvider.read_from_file(dm_filepath)
    else:
        logging.info("Using provided travel time provider")

    logging.info("Reading DARP instance from: {}".format(os.path.realpath(demand_path)))

    with open(demand_path, "r", encoding="utf-8") as demand_file:
        file_begin = demand_file.tell()
        header = demand_file.readline()
        demand_file.seek(file_begin)
        time_loader = None
        if ',' in header:
            time_loader = TimeLoader()
            requests = load_demand(demand_file, instance_config, travel_time_provider, time_loader)
        else:
            instance_time = None
            if 'min_time' in instance_config['demand']:
                instance_time = _load_datetime(instance_config['demand']['min_time'])
            elif 'vehicles' in instance_config:
                if 'operation_start' in instance_config['vehicles']:
                    instance_time = _load_datetime(instance_config['vehicles']['operation_start'])
                elif 'start_time' in instance_config['vehicles']:
                    instance_time = instance_config['vehicles']['start_time']
            if instance_time is None:
                time_loader = TimeLoader()
            else:
                instance_date = datetime.combine(instance_time.date(), time(), tzinfo=timezone.utc)
                time_loader = TimeLoader(instance_date)
            requests = load_demand_legacy(demand_file, instance_config, travel_time_provider, demand_path, time_loader)

    max_pickup_delay = instance_config.get('max_pickup_delay', 0)
    enable_negative_delay = instance_config.get('enable_negative_delay', False)

    start_time = instance_config.get('start_time', datetime.fromtimestamp(0, tz=timezone.utc))
    min_pause_length = 0
    max_pause_interval = 0
    vehicle_capacity = None  # by default, each vehicle defines its own capacity
    vehicle_capital_cost = None
    if 'vehicles' in instance_config:
        min_pause_length = instance_config['vehicles'].get('min_pause_length', 0)
        max_pause_interval = instance_config['vehicles'].get('max_pause_interval', 0)

        if 'capacity' in instance_config['vehicles']:
            vehicle_capacity = instance_config['vehicles']['capacity']
        if 'capital_cost' in instance_config['vehicles']:
            vehicle_capital_cost = instance_config['vehicles']['capital_cost']

    travel_time_divider = instance_config.get('travel_time_divider', 1)
    relative_delay_cost = instance_config.get('demand', {}).get('relative_delay_cost', 0)
    problem = instance_problem_from_config(instance_config)

    darp_instance_config = DARPInstanceConfiguration(
        0,
        0,
        False,
        False,
        start_time,
        min_pause_length,
        max_pause_interval,
        travel_time_divider,
        max_pickup_delay,
        enable_negative_delay,
        vehicle_capacity,
        vehicle_capital_cost,
        relative_delay_cost,
        problem,
    )
        
    darp_instance = DARPInstance(requests, vehicles, travel_time_provider, darp_instance_config)
    
    return darp_instance, time_loader
