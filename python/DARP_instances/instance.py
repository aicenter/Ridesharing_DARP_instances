# from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd
from numpy import round, ceil
from typing import Iterable, Dict
from abc import ABC, abstractmethod
from enum import Enum, auto
import logging
from functools import singledispatchmethod
import yaml
import h5py

import darpbenchmark.log


class Coordinate(ABC):
    @abstractmethod
    def get_x(self) -> float:
        pass

    @abstractmethod
    def get_y(self) -> float:
        pass


class ActionType(Enum):
    PICKUP = auto()
    DROP_OFF = auto()


class Action:
    def __init__(self, action_id, node, min_time: int, max_time: int, action_type: ActionType,
                 request, service_time: int = 0):
        self.id = action_id
        self.node = node
        self.min_time = min_time
        self.max_time = max_time
        self.action_type = action_type
        self.request = request
        self.service_time = service_time

    def __str__(self):
        return ('{} {} [{}, {}], {};'.format(self.id, self.action_type, self.min_time, self.max_time, self.node))


class Request:
    def __init__ (self, index: int, pickup_id: int, pickup_node, pickup_min_time: int, pickup_max_time: int,
                  dropoff_id: int, drop_off_node, drop_off_min_time: int,
                  drop_off_max_time: int, min_travel_time: int, pickup_service_time: int = 0, drop_off_service_time: int = 0):
        self.index = index
        self.pickup_action \
            = Action(pickup_id, pickup_node, pickup_min_time, pickup_max_time,
                     ActionType.PICKUP, self, pickup_service_time)
        self.drop_off_action \
            = Action(dropoff_id, drop_off_node, drop_off_min_time, drop_off_max_time,
                     ActionType.DROP_OFF, self, drop_off_service_time)
        self.min_travel_time = min_travel_time


class Vehicle:
    def __init__(self, index: int, initial_position, capacity: int):
        self.index = index
        self.initial_position = initial_position
        self.capacity = capacity


class VirtualVehicle(Vehicle):
    def __init__(self, capacity: int, time_start):
        super().__init__(0, None, capacity)
        self.time_to_start = time_start


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