from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import List
from datetime import datetime


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
    def __init__(self, action_id, node, min_time: datetime, max_time: datetime, action_type: ActionType,
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
    def __init__ (self, index: int, pickup_id: int, pickup_node, pickup_min_time: datetime, pickup_max_time: datetime,
                  dropoff_id: int, drop_off_node, drop_off_min_time: datetime,
                  drop_off_max_time: datetime, min_travel_time: int, pickup_service_time: int = 0, drop_off_service_time: int = 0, equipment: int = 0, vehicle_id: int = 0):
        self.index = index
        self.pickup_action \
            = Action(pickup_id, pickup_node, pickup_min_time, pickup_max_time,
                     ActionType.PICKUP, self, pickup_service_time)
        self.drop_off_action \
            = Action(dropoff_id, drop_off_node, drop_off_min_time, drop_off_max_time,
                     ActionType.DROP_OFF, self, drop_off_service_time)
        self.min_travel_time = min_travel_time
        self.equipment = equipment
        self.vehicle_id = vehicle_id


class Vehicle:
    def __init__(self, index: int, initial_position, capacity: int, configurations: List[List[int]], operation_start: datetime, operation_end: datetime):
        self.index = index
        self.initial_position = initial_position
        self.capacity = capacity
        self.configurations = configurations
        self.operation_start = operation_start
        self.operation_end = operation_end


class VirtualVehicle(Vehicle):
    def __init__(self, capacity: int, time_start):
        super().__init__(0, None, capacity)
        self.time_to_start = time_start