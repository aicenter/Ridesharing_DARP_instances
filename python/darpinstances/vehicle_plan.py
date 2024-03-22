
from typing import List, Optional, Dict
from datetime import datetime

from darpinstances.instance import Vehicle
from darpinstances.instance_generation.instance_objects import Action


class ActionData:
    def __init__(self, action: Action, arrival_time: Optional[datetime] = None, departure_time: Optional[datetime] = None):
        self.action = action
        self.arrival_time = arrival_time
        self.departure_time = departure_time
        self.other_index: Optional[int] = None
        self.position: Optional[int] = None

    def get_max_time(self) -> int:
        return self.action.max_time

    def get_service_duration(self) -> int:
        return self.action.service_time


class VehiclePlan:

    def get_departure_time(self):
        return self.departure_time

    def get_arrival_time(self):
        return self.arrival_time

    def __init__(self, vehicle: Vehicle, cost: int, actions: List[ActionData], departure_time: Optional[datetime] = None, arrival_time: Optional[datetime] = None):
        self.departure_time = departure_time
        self.arrival_time = arrival_time
        self.actions = actions
        self.vehicle = vehicle
        self.cost = cost

    def __str__(self):
        return 'plan: {} Cost {}'.format(' '.join([str(a) for a in self.actions]), self.cost)
