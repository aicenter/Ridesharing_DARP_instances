from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import List, Optional, Set
from datetime import datetime


class Demand:
    """
    Composite resource demand of one request. A standard passenger occupies one
    regular seat, a wheelchair user occupies one wheelchair slot (independent of
    regular seats), and a child in a child seat occupies one regular seat AND one
    child seat unit (the child seat is equipment installed on a regular seat).
    """

    def __init__(self, standard: int = 1, wheelchairs: int = 0, children_in_seat: int = 0):
        self.standard = standard
        self.wheelchairs = wheelchairs
        self.children_in_seat = children_in_seat

    @property
    def seats_needed(self) -> int:
        return self.standard + self.children_in_seat

    @property
    def total_travellers(self) -> int:
        return self.standard + self.wheelchairs + self.children_in_seat

    def __repr__(self):
        return f"Demand(standard={self.standard}, wheelchairs={self.wheelchairs}, children_in_seat={self.children_in_seat})"


class RequestConstraints:
    """
    Effective per-request constraint limits, merged from the instance config
    baseline and the per-request override columns. A value of None means the
    constraint is disabled for this request.

    Both delay constraints follow the unified semantics:
    - max_delay is anchored to the REQUESTED pickup time and is therefore
      expressed in the derived action max times (window-based),
    - max_travel_delay is anchored to the ACTUAL pickup and bounds
      ride_time - min_travel_time during the plan walk.
    """

    def __init__(
        self,
        max_travel_delay: Optional[float] = None,
        max_ride_time: Optional[int] = None,
        max_walking_distance: Optional[float] = None,
        required_arrival_time: Optional[datetime] = None,
        resolved: bool = False,
    ):
        self.max_travel_delay = max_travel_delay
        self.max_ride_time = max_ride_time
        self.max_walking_distance = max_walking_distance
        self.required_arrival_time = required_arrival_time
        # True when the loader merged the config baseline into these values;
        # legacy loaders leave this False so instance-level limits still apply
        self.resolved = resolved


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
    def __init__(
        self,
        action_id,
        node,
        min_time: datetime,
        max_time: datetime,
        action_type: ActionType,
        request: 'Request',
        service_time: int = 0
    ):
        self.id = action_id
        self.node = node
        self.min_time = min_time
        self.max_time = max_time
        self.action_type = action_type
        self.request: Request = request
        self.service_time = service_time

    def __str__(self):
        return ('{} {} [{}, {}], {};'.format(self.id, self.action_type, self.min_time, self.max_time, self.node))


class Request:
    def __init__(
        self,
        index: int,
        pickup_id: int,
        pickup_node,
        pickup_min_time: datetime,
        pickup_max_time: datetime,
        dropoff_id: int,
        drop_off_node,
        drop_off_max_time: datetime,
        min_travel_time: int,
        pickup_service_time: int = 0,
        drop_off_service_time: int = 0,
        equipment: int = 0,
        required_vehicle_id: Optional[int] = None,
        demand: Optional[Demand] = None,
        exclusive: bool = False,
        required_equipment: Optional[Set[str]] = None,
        constraints: Optional[RequestConstraints] = None,
        walk_to_origin: float = 0.0,
        walk_from_destination: float = 0.0,
    ):
        self.index = index
        self.pickup_action = Action(
            pickup_id, pickup_node, pickup_min_time, pickup_max_time, ActionType.PICKUP, self, pickup_service_time
        )
        self.drop_off_action = Action(
            dropoff_id,
            drop_off_node,
            None,
            drop_off_max_time,
            ActionType.DROP_OFF,
            self,
            drop_off_service_time
        )
        self.min_travel_time = min_travel_time
        self.equipment = equipment
        self.required_vehicle_id = required_vehicle_id
        self.demand = demand if demand is not None else Demand()
        self.exclusive = exclusive
        self.required_equipment = required_equipment if required_equipment is not None else set()
        self.constraints = constraints if constraints is not None else RequestConstraints()
        self.walk_to_origin = walk_to_origin
        self.walk_from_destination = walk_from_destination

    def __eq__(self, other):
        return self.index == other.index

    def __hash__(self):
        return hash(self.index)


class Vehicle:
    def __init__(
        self,
        index: int,
        initial_position,
        capacity: int,
        configurations: List[List[int]] = [],
        operation_start: datetime = None,
        operation_end: datetime = None,
        wheelchair_slots: int = 0,
        child_seats: int = 0,
        equipment: Optional[Set[str]] = None,
        max_drive_time: Optional[int] = None,
        max_drive_time_without_pause: Optional[int] = None,
        min_pause: Optional[int] = None,
        return_to_depot: Optional[bool] = None,
    ):
        self.index = index
        self.initial_position = initial_position
        self.capacity = capacity
        self.configurations = configurations
        self.operation_start = operation_start
        self.operation_end = operation_end
        # typed resources: wheelchair slots are dedicated space outside regular
        # seats; child seats are equipment units installed on regular seats
        self.wheelchair_slots = wheelchair_slots
        self.child_seats = child_seats
        # named equipment flags matched against request.required_equipment (superset check)
        self.equipment = equipment if equipment is not None else set()
        # driver rules, all in seconds
        self.max_drive_time = max_drive_time
        self.max_drive_time_without_pause = max_drive_time_without_pause
        self.min_pause = min_pause
        # per-vehicle override of the instance-level return_to_depot setting
        self.return_to_depot = return_to_depot


class VirtualVehicle(Vehicle):
    def __init__(self, capacity: int, time_start):
        super().__init__(0, None, capacity)
        self.time_to_start = time_start