# from __future__ import annotations
from datetime import datetime, timedelta

import math
import os

import numpy as np
import pandas as pd
from numpy import round, ceil
from typing import Iterable, Dict, List, Optional
from abc import ABC, abstractmethod
from enum import Enum, auto
import logging
from functools import singledispatchmethod
import yaml
import h5py
from pathlib import Path

import darpinstances.log
from darpinstances.inout import check_file_exists
from darpinstances.instance_generation.instance_objects import Coordinate, Request, Vehicle


class TravelTimeProvider(ABC):

    @abstractmethod
    def get_travel_time(self, from_position, to_position) -> int:
        """
        Provides travel time in arbitrary units between location @param from and @param to.
        :param from_position:
        :param to_position:
        :return: Travel time between location @param from and @param to in milliseconds.
        """
        pass


class EuclideanTravelTimeProvider(TravelTimeProvider):
    """
    Attributes
    coordinate resolution: int
        How many milliseconds should it take to travel by 1 in the coordinate system
    """

    def __init__(self, coordinate_resolution: int):
        self.coordinate_resolution = coordinate_resolution

    def get_travel_time(self, from_position: Coordinate, to_position: Coordinate):
        distance = math.sqrt(math.pow(from_position.get_x() - to_position.get_x(), 2)
                             + math.pow(from_position.get_y() - to_position.get_y(), 2))
        travel_time = round(distance * self.coordinate_resolution)
        return travel_time


class MatrixTravelTimeProvider(TravelTimeProvider):
    """

    """
    @classmethod
    def from_csv(cls, path_to_dm: str):
        dm = pd.read_csv(path_to_dm, header=None, dtype=np.int32)
        return cls(dm.values)

    @classmethod
    def from_hdf(cls, path_to_dm: str):
        # dm = pd.read_hdf(path_to_dm, dtype=np.int32)
        with h5py.File(path_to_dm, 'r') as dm_file:
            a_group_key = list(dm_file.keys())[0]
            dm_arr = dm_file[a_group_key][()]
            return cls(dm_arr)

    def __init__(self, dm: np.ndarray):
        self.dm = dm

    @singledispatchmethod
    def get_travel_time(self, from_index: int, to_index: int):
        return self.dm[from_index][to_index]

    @classmethod
    def read_from_file(cls, dm_filepath: str):
        if dm_filepath.endswith('csv'):
            return cls.from_csv(dm_filepath)
        else:
            return cls.from_hdf(dm_filepath)


class DARPInstanceConfiguration:
    def __init__(
        self,
        max_route_duration: int,
        max_ride_time: int,
        return_to_depot: bool = True,
        virtual_vehicles: bool = False,
        start_time: Optional[datetime] = None,
        min_pause_length: int = 0,
        max_pause_interval: int = 0,
     ):
        self.max_route_duration = max_route_duration
        self.max_ride_time = max_ride_time
        self.return_to_depot = return_to_depot
        self.virtual_vehicles = virtual_vehicles
        self.start_time = start_time
        self.min_pause_length = min_pause_length
        self.max_pause_interval = max_pause_interval


class DARPInstance:

    def __init__(
        self,
        requests: Iterable[Request],
        vehicles: Iterable[Vehicle],
        travel_time_provider: TravelTimeProvider,
        darp_instance_config: DARPInstanceConfiguration
    ):
        self.requests = requests
        self.vehicles = vehicles
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


def load_instance_config(config_file_path: Path) -> Dict:
    config_file_path_abs = config_file_path.absolute()
    logging.info(f"Loading instance config from {config_file_path_abs}")
    with open(config_file_path_abs, 'r') as config_file:
        try:
            config = yaml.safe_load(config_file)

            defaults = {
                'instance_dir': os.path.dirname(config_file_path),
                'map': {
                    'path': config_file_path.parent / 'map'
                },
                'demand': {
                    'type': 'generate',
                    'min_time': 0,
                    'max_time': 86_400  # 24:00
                },
                'vehicles': {
                    'start_time': config['demand']['min_time']
                }
            }

            _set_config_defaults(config, defaults)
            return config
        except yaml.YAMLError as er:
            logging.error(er)


class Node:
    def get_idx(self) -> int:
        return self.idx

    def __init__(self, idx: int):
        self.idx = idx

    def __str__(self):
        return str(self.idx)


def load_vehicles(vehicles_path: str) -> List[Vehicle]:
    veh_data = darpinstances.inout.load_csv(vehicles_path, "\t")
    vehicles = []
    for index, veh in enumerate(veh_data):
        vehicles.append(Vehicle(index, Node(int(veh[0])), int(veh[1])))

    return vehicles

class EquipmentType(Enum):
    NONE = 0
    STANDARD_SEAT = 1
    WHEELCHAIR = 2
    ELECTRIC_WHEELCHAIR = 3
    MEDICAL_STROLLER = 4


def map_equipment_type(equipment_str: str) -> EquipmentType:
    equipment_mapping = {
        "NONE": EquipmentType.NONE,
        "STANDARD_SEAT": EquipmentType.STANDARD_SEAT,
        "WHEELCHAIR": EquipmentType.WHEELCHAIR,
        "ELECTRIC_WHEELCHAIR": EquipmentType.ELECTRIC_WHEELCHAIR,
        "MEDICAL_STROLLER": EquipmentType.MEDICAL_STROLLER
    }
    return equipment_mapping.get(equipment_str, EquipmentType.NONE)

def _load_datetime(string: str):
    return datetime.strptime(string, '%Y-%m-%d %H:%M:%S')


def load_vehicles_from_json(vehicles_path: str) -> List[Vehicle]:
    veh_data = darpinstances.inout.load_json(vehicles_path)
    vehicles = []
    list = veh_data["vehicles"]
    for index, veh in enumerate(list):
        configurations = []
        if "slots" in veh:
            equipment = []
            for item in veh["slots"]:
                count = int(item["count"])
                equipmentType = map_equipment_type(item["type"])
                for n in range(count):
                    equipment.append(equipmentType.value)
            configurations.append(equipment)
        elif "configurations" in veh:
            equipment_list = [equipment.name for equipment in EquipmentType]
            for item in veh["configurations"]:
                configuration_equipment = []
                for equipment_name in equipment_list:
                    equipmentType = map_equipment_type(equipment_name)
                    count = int(item.get(equipment_name, 0))
                    for i in range(count):
                        configuration_equipment.append(equipmentType.value)
                configurations.append(configuration_equipment)
        config_capacities = [len(config) for config in configurations]
        max_capacity = max(config_capacities) if config_capacities else 0
        capacity = veh["capacity"] if "capacity" in veh else max_capacity
        operation_start = _load_datetime(veh["operation_start"]) if "operation_start" in veh else None
        operation_end = _load_datetime(veh["operation_end"]) if "operation_end" in veh else None
        vehicles.append(Vehicle(index, Node(int(veh["station_index"])), capacity, configurations, operation_start, operation_end))

    return vehicles


def read_instance(filepath: Path, travel_time_provider: MatrixTravelTimeProvider = None) -> DARPInstance:
    instance_config = load_instance_config(filepath)
    instance_dir_path = os.path.dirname(filepath)

    # Here, we are completing the possibly relative paths. Therefore, we need to change the dir because dm path
    # loaded from instance config is relative to the instance dir
    os.chdir(instance_dir_path)
    instance_path = instance_config['demand']['filepath']
    check_file_exists(instance_path)

    vehicles_path_csv = os.path.join(instance_dir_path, 'vehicles.csv')
    vehicles_path_json = os.path.join(instance_dir_path, 'vehicles.json')
    csv_exists = check_file_exists(vehicles_path_csv, raise_ex=False)
    json_exists = check_file_exists(vehicles_path_json, raise_ex=False)

    # dm loading
    if travel_time_provider is None:
        if 'dm_filepath' in instance_config:
            dm_filepath = instance_config['dm_filepath']
        # by default, the dm is located in the are folder
        else:
            dm_filepath = os.path.join(instance_config['area_dir'], 'dm.h5')
        check_file_exists(dm_filepath)
        logging.info("Reading dm from: {}".format(os.path.realpath(dm_filepath)))
        travel_time_provider = MatrixTravelTimeProvider.read_from_file(dm_filepath)
    else:
        logging.info("Using provided travel time provider")

    logging.info("Reading DARP instance from: {}".format(os.path.realpath(instance_path)))
    with open(instance_path, "r", encoding="utf-8") as infile:
        if json_exists:
            vehicles = load_vehicles_from_json(vehicles_path_json)
        elif csv_exists:
            vehicles = load_vehicles(vehicles_path_csv)
        else:
            raise ValueError("Vehicles file .json or .csv was not found")

        requests: List[Request] = []

        line_string = infile.readline()
        line_string = infile.readline()
        action_id = 0
        index = 0
        while (line_string):
            line = line_string.split()
            request_id: int = int(index)
            if isinstance(line[0], int):
                request_time = datetime.fromtimestamp(int(line[0]) / 1000)
            else:
                request_time = _load_datetime(line[0])

            start_node = Node(int(line[1]))
            end_node = Node(int(line[2]))
            equipment = map_equipment_type(line[4]).value if(len(line) > 4) else 0
            min_travel_time = travel_time_provider.get_travel_time(start_node, end_node)
            max_pickup_time = request_time + timedelta(seconds=int(instance_config['max_prolongation']))
            min_drop_off_time = request_time + timedelta(seconds=min_travel_time)
            max_drop_off_time = max_pickup_time + timedelta(seconds=min_travel_time)

            vehicle_id = int(line[5]) if(len(line) > 5) else 0
            requests.append(Request(request_id, action_id, start_node, request_time, max_pickup_time,
                                    action_id + 1, end_node, min_drop_off_time,  max_drop_off_time,
                                    min_travel_time, 0, 0, equipment, vehicle_id))
            line_string = infile.readline()
            action_id += 2
            index += 1

        start_time_val = instance_config['vehicles']['start_time']
        min_pause_length = instance_config['vehicles'].get('min_pause_length', 0)
        max_pause_interval = instance_config['vehicles'].get('max_pause_interval', 0)

        if isinstance(start_time_val, int):
            start_time = datetime.fromtimestamp(start_time_val)
        else:
            start_time = _load_datetime(start_time_val)

        config = DARPInstanceConfiguration(0, 0, False, False, start_time, min_pause_length, max_pause_interval)
        return DARPInstance(requests, vehicles, travel_time_provider, config)


@MatrixTravelTimeProvider.get_travel_time.register
def _(self, from_node: Node, to_dode: Node):
    return self.get_travel_time(from_node.idx, to_dode.idx)
