from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Set
from datetime import datetime

# The fixed slot-type vocabulary: every passenger occupies exactly one slot of
# their type for the whole ride, and vehicle seating configurations are counts
# over these types. Children in child seats are NOT a slot type — a child seat
# is equipment mounted on a standard seat, so a child in a seat occupies one
# standard slot plus one child-seat unit (a separate vehicle-level count).
SLOT_TYPES = ("standard", "wheelchair", "electric_wheelchair", "stroller")


@dataclass(frozen=True)
class Passengers:
    """
    The travelling group of one request, as counts per slot type, plus the
    number of children travelling in child seats. Defaults to a single
    standard passenger.
    """

    standard: int = 1
    wheelchair: int = 0
    electric_wheelchair: int = 0
    stroller: int = 0
    children_in_seat: int = 0

    @property
    def slot_demand(self) -> Dict[str, int]:
        """Occupied slots per slot type (children occupy standard seats)."""
        return {
            "standard": self.standard + self.children_in_seat,
            "wheelchair": self.wheelchair,
            "electric_wheelchair": self.electric_wheelchair,
            "stroller": self.stroller,
        }

    @property
    def total_travellers(self) -> int:
        return (
            self.standard
            + self.wheelchair
            + self.electric_wheelchair
            + self.stroller
            + self.children_in_seat
        )


class RequestConstraints:
    """
    Effective per-request constraints, merged from the instance config baseline
    and the per-request override columns. A limit value of None means the
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
        max_earliness: Optional[float] = None,
        required_vehicle_id: Optional[int] = None,
        exclusive: bool = False,
        required_equipment: Optional[Set[str]] = None,
    ):
        self.max_travel_delay = max_travel_delay
        self.max_ride_time = max_ride_time
        self.max_walking_distance = max_walking_distance
        self.required_arrival_time = required_arrival_time
        # True when the loader merged the config baseline into these values;
        # legacy loaders leave this False so instance-level limits still apply
        self.resolved = resolved
        # symmetric earliness bound before required_arrival_time; resolved
        # loaders default it to max_travel_delay (the historical behaviour),
        # None with resolved=True means "earliness unbounded"
        self.max_earliness = max_earliness
        # per-request hard constraints on the assignment (no config baseline):
        # only this vehicle may serve the request / no ride-sharing while the
        # request is onboard / named equipment the vehicle must carry
        self.required_vehicle_id = required_vehicle_id
        self.exclusive = exclusive
        self.required_equipment = required_equipment if required_equipment is not None else set()


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
        passengers: Passengers = Passengers(),
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
        self.passengers = passengers
        self.constraints = constraints if constraints is not None else RequestConstraints()
        # actual walking distances of this request's rider (metres); the LIMIT
        # they are checked against lives in constraints.max_walking_distance
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
        configurations: List[Dict[str, int]],
        operation_start: datetime = None,
        operation_end: datetime = None,
        child_seats: int = 0,
        equipment: Optional[Set[str]] = None,
        max_drive_time: Optional[int] = None,
        max_drive_time_without_pause: Optional[int] = None,
        min_pause: Optional[int] = None,
        return_to_depot: Optional[bool] = None,
        cost_return_to_depot: bool = False,
    ):
        self.index = index
        self.initial_position = initial_position
        # alternative seating configurations, each a slot-type -> count dict
        # (see SLOT_TYPES). The onboard load must fit within at least one
        # configuration at every stop; the fitting configuration may differ
        # between stops (configurations model shared physical spots, e.g. one
        # bay taking either a stroller or a wheelchair)
        self.configurations = configurations
        self.operation_start = operation_start
        self.operation_end = operation_end
        # child seats are equipment units installed on standard seats, tracked
        # as a plain count outside the configurations
        self.child_seats = child_seats
        # named equipment flags matched against the requests' required equipment (superset check)
        self.equipment = equipment if equipment is not None else set()
        # driver rules, all in seconds
        self.max_drive_time = max_drive_time
        self.max_drive_time_without_pause = max_drive_time_without_pause
        self.min_pause = min_pause
        # per-vehicle override of the instance-level return_to_depot setting
        self.return_to_depot = return_to_depot
        # when True and the effective return_to_depot is False, the depot-return
        # leg is INCLUDED in the cost components (travel time, distance, plan
        # duration) but NOT constraint-checked — the vehicle physically returns
        # even though no constraint requires it to make it back by shift end
        self.cost_return_to_depot = bool(cost_return_to_depot)

    @property
    def capacity(self) -> int:
        """Largest standard-seat count over the configurations (legacy shorthand)."""
        return max((config.get("standard", 0) for config in self.configurations), default=0)


class VirtualVehicle(Vehicle):
    def __init__(self, capacity: int, time_start):
        super().__init__(0, None, [{"standard": capacity}])
        self.time_to_start = time_start
