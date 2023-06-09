# from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd
from numpy import round, ceil
from typing import Iterable, Dict, List
from abc import ABC, abstractmethod
from enum import Enum, auto
import logging
from functools import singledispatchmethod
import yaml
import h5py

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
        start_time: int = 0
     ):
        self.max_route_duration = max_route_duration
        self.max_ride_time = max_ride_time
        self.return_to_depot = return_to_depot
        self.virtual_vehicles = virtual_vehicles
        self.start_time = start_time


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


def load_instance_config(config_file_path: str) -> Dict:
    config_file_path_abs = os.path.abspath(config_file_path)
    logging.info(f"Loading instance config from {config_file_path_abs}")
    with open(config_file_path_abs, 'r') as config_file:
        try:
            config = yaml.safe_load(config_file)

            defaults = {
                'instance_dir': os.path.dirname(config_file_path),
                'map': {
                    'path': os.path.join(config['area_dir'], 'map')
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


def read_instance(filepath: str) -> DARPInstance:
    instance_config = load_instance_config(filepath)
    instance_dir_path = os.path.dirname(filepath)

    # Here, we are completing the possibly relative paths. Therefore, we need to change the dir because dm path
    # loaded from instance config is relative to the instance dir
    os.chdir(instance_dir_path)
    instance_path = instance_config['demand']['filepath']
    check_file_exists(instance_path)

    if 'dm_filepath' in instance_config:
        dm_filepath = instance_config['dm_filepath']
    # by default, the dm is located in the are folder
    else:
        dm_filepath = os.path.join(instance_config['area_dir'], 'dm.h5')
    check_file_exists(dm_filepath)

    vehicles_path = os.path.join(instance_dir_path, 'vehicles.csv')
    check_file_exists(vehicles_path)

    logging.info("Reading dm from: {}".format(os.path.realpath(dm_filepath)))
    travel_time_provider = MatrixTravelTimeProvider.read_from_file(dm_filepath)

    logging.info("Reading DARP instance from: {}".format(os.path.realpath(instance_path)))
    with open(instance_path, "r", encoding="utf-8") as infile:
        vehicles = load_vehicles(vehicles_path)

        requests: List[Request] = []

        line_string = infile.readline()
        action_id = 0
        while (line_string):
            line = line_string.split()
            request_id: int = int(line[0])
            request_time: int = int(line[1]) / 1000
            start_node = Node(int(line[2]))
            end_node = Node(int(line[3]))
            min_travel_time = travel_time_provider.get_travel_time(start_node, end_node)
            max_pickup_time = request_time + int(instance_config['max_prolongation'])
            requests.append(Request(request_id, action_id, start_node, request_time, max_pickup_time,
                                    action_id + 1, end_node, request_time + min_travel_time,  max_pickup_time + min_travel_time,
                                    min_travel_time))
            line_string = infile.readline()
            action_id += 2

        start_time = instance_config['vehicles']['start_time']
        if not isinstance(start_time, int):
            # start_datetime = datetime.strptime(start_time)
            timeparts = start_time.split(' ')[1].split(':')
            h = timeparts[0]
            m = timeparts[1]
            s = 0 if len(timeparts) == 2 else timeparts[2]
            start_time = int(h) * 3600 + int(m) * 60 + int(s)

        config = DARPInstanceConfiguration(0, 0, False, False, start_time)
        return DARPInstance(requests, vehicles, travel_time_provider, config)


@MatrixTravelTimeProvider.get_travel_time.register
def _(self, from_node: Node, to_dode: Node):
    return self.get_travel_time(from_node.idx, to_dode.idx)


