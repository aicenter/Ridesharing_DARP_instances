"""
Travel time providers for DARP instances.
"""
import math
from abc import ABC, abstractmethod
from functools import singledispatchmethod
from pathlib import Path
import h5py
import numpy as np
import pandas as pd

from darpinstances.instance_objects import Coordinate


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
        distance = math.sqrt(
            math.pow(from_position.get_x() - to_position.get_x(), 2)
            + math.pow(from_position.get_y() - to_position.get_y(), 2)
        )
        travel_time = round(distance * self.coordinate_resolution)
        return travel_time


class MatrixTravelTimeProvider(TravelTimeProvider):
    """Travel time from a precomputed distance/travel-time matrix."""

    @classmethod
    def from_csv(cls, path_to_dm: Path, dtype=np.int32):
        # travel time matrices are integer seconds; distance matrices may carry
        # full-precision floats (metres), so the dtype is overridable
        dm = pd.read_csv(path_to_dm, header=None, dtype=dtype)
        return cls(dm.values)

    @classmethod
    def from_hdf(cls, path_to_dm: Path):
        with h5py.File(path_to_dm, 'r') as dm_file:
            if 'dm' in dm_file:
                dataset_name = 'dm'
            else:
                dataset_name = list(dm_file.keys())[0]
            dm_arr = dm_file[dataset_name][()]
            return cls(dm_arr)

    def __init__(self, dm: np.ndarray):
        self.dm = dm

    @singledispatchmethod
    def get_travel_time(self, from_index: int, to_index: int):
        return self.dm[from_index][to_index]

    @classmethod
    def read_from_file(cls, dm_filepath: Path, dtype=np.int32):
        if dm_filepath.suffix == '.csv':
            return cls.from_csv(dm_filepath, dtype=dtype)
        else:
            return cls.from_hdf(dm_filepath)

    def get_node_count(self):
        return len(self.dm)


class GridTravelTimeProvider(TravelTimeProvider):
    """
    Travel time on a 2D square grid. Nodes are indexed in row-major order from 0 to grid_size² - 1.
    Travel time between horizontally or vertically neighboring nodes is `travel_time_between_neighbors`;
    for non-adjacent nodes, travel time is Manhattan distance times that value.
    """

    def __init__(self, grid_size: int, travel_time_between_neighbors: int):
        self.grid_size = grid_size
        self.travel_time_between_neighbors = travel_time_between_neighbors

    @singledispatchmethod
    def get_travel_time(self, from_index: int, to_index: int) -> int:
        r1, c1 = from_index // self.grid_size, from_index % self.grid_size
        r2, c2 = to_index // self.grid_size, to_index % self.grid_size
        manhattan = abs(r1 - r2) + abs(c1 - c2)
        return manhattan * self.travel_time_between_neighbors

    def get_node_count(self) -> int:
        return self.grid_size * self.grid_size
