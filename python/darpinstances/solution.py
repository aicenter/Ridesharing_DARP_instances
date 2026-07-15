import logging
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Set, Tuple, Dict, Iterable, List, Union
import pandas as pd
from pandera.typing import Series

from darpinstances.inout import load_json
from darpinstances.instance import DARPInstance, Request, Vehicle
from darpinstances.instance_objects import ActionType, Action
from darpinstances.utils import TimeLoader
from darpinstances.vehicle_plan import VehiclePlan, ActionData


def _nodes_equal(a, b) -> bool:
    """Compare two node/position values: int (node index) or Coordinate (Cordeau)."""
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if hasattr(a, 'get_x') and hasattr(b, 'get_x'):
        return a.get_x() == b.get_x() and a.get_y() == b.get_y()
    return a == b


def _node_repr(n) -> str:
    """String representation for logging: int or Coordinate."""
    if isinstance(n, int):
        return str(n)
    if hasattr(n, 'get_x'):
        return "({},{})".format(n.get_x(), n.get_y())
    return str(n)


class Solution:
    def __init__(
        self,
        vehicle_plans: Iterable[VehiclePlan],
        cost: Optional[int],
        dropped_requests=Optional[Set[int]],
        feasible=True
    ):
        """
        Constructor
        :param vehicle_plans: List of vehicle plans
        :param cost: Total cost
        :param dropped_requests: Set of dropped requests' indices
        """
        self.vehicle_plans = vehicle_plans
        self.cost = cost
        self.feasible = feasible
        if dropped_requests is None:
            self.dropped_requests = []
        else:
            self.dropped_requests = dropped_requests

    @classmethod
    def make_infeasible(cls):
        return cls([], 0, None, False)

    def __str__(self):
        return 'solution: cost {}.\nPlans: {}.'.format(self.cost, '\n'.join([str(p) for p in self.vehicle_plans]))


class LoadingError(Enum):
    ACTION_MIN_TIME_MISMATCH = auto()
    ACTION_MAX_TIME_MISMATCH = auto()
    ACTION_POSITION_MISMATCH = auto()
    NODE_MISMATCH = auto()
    REQUEST_SERVED_TWICE = auto()


class SolutionLoader:
    def __init__(self, max_error_count: int = 10, time_loader: TimeLoader = None):
        self.error_count = 0
        self.max_error_count = max_error_count
        self.errors = {error_type: 0 for error_type in LoadingError}
        self.time_loader = time_loader

    def _increment_error(self, error_type: LoadingError = None):
        self.error_count += 1
        if error_type:
            self.errors[error_type] += 1
        if self.error_count > self.max_error_count:
            raise RuntimeError(f"Error count ({self.error_count}) exceeded maximum allowed errors ({self.max_error_count})")


    def load_solution(self, filepath: Path, instance: DARPInstance, fleet_sizing: bool = False) -> Solution:
        request_map, vehicle_map = _prepare_maps(instance)

        logging.info(f"Loading solution from {filepath}")

        if filepath.suffix == '.json':
            return self.load_json_solution(
                filepath,
                instance.darp_instance_config.virtual_vehicles,
                request_map,
                vehicle_map,
                fleet_sizing=fleet_sizing,
            )
        elif filepath.suffix.lower() == '.csv':
            peek = pd.read_csv(filepath, nrows=0)
            # Use simple format (plan, request) when first column name is "plan"
            if len(peek.columns) > 0 and peek.columns[0] == "plan":
                return self.load_simple_csv_solution(filepath, instance, fleet_sizing=fleet_sizing)
            else:
                solution, vehicles = self.load_csv_solution(
                    filepath,
                    request_map,
                    instance.darp_instance_config.start_time,
                    instance.darp_instance_config.vehicle_capacity
                )
                instance.vehicles = vehicles
                return solution

    def load_json_solution(
        self, filepath, use_virtual_vehicles, request_map, vehicle_map, fleet_sizing: bool = False
    ):
        json_data = load_json(filepath)

        # handle infesible solutions
        if "feasible" in json_data and json_data["feasible"] == False:
            return Solution.make_infeasible()

        vehicle_plans = []
        total_missmatch_actions = 0
        for json_plan in json_data["plans"]:
            plan, mismatch_actions_count = self._load_plan(
                json_plan, use_virtual_vehicles, vehicle_map, request_map, fleet_sizing=fleet_sizing
            )
            vehicle_plans.append(plan)
            total_missmatch_actions += mismatch_actions_count

        if total_missmatch_actions > 0:
            logging.warning(f"Mismatch in actions found in the solution file. Total mismatch count: {total_missmatch_actions}")
            self._increment_error()

        dropped_requests = set()
        for request in json_data["dropped_requests"]:
            # the schema requires "index"; "id" is accepted for backward compatibility
            key = "index" if "index" in request else "id"
            dropped_requests.add(int(request[key]))
        return Solution(vehicle_plans, json_data["cost"], dropped_requests)

    def load_csv_solution(self, filepath, request_map, simulation_start_time: datetime, vehicle_capacity: int) \
        -> Tuple[Solution, Series[Vehicle]]:
        data = pd.read_csv(filepath)

        vehicles = data[data['action'] == 'E'][['vehicle_id', 'node_id', 'time']].apply(
            _load_vehicle_from_csv, axis=1, args=(simulation_start_time, vehicle_capacity)
        )

        vehicle_map = dict()
        for vehicle in vehicles:
            vehicle_map[vehicle.index] = vehicle

        vehicle_plans = data.groupby("vehicle_id").apply(
            lambda x: self._load_plan_from_csv(x, request_map, vehicle_map, simulation_start_time)
        )
        # remove empty plans
        non_empty_vehicle_plans = vehicle_plans[vehicle_plans.notnull()]
        if len(non_empty_vehicle_plans) != len(vehicle_plans):
            logging.warning("%d empty plans were removed", len(vehicle_plans) - len(non_empty_vehicle_plans))

        return Solution(non_empty_vehicle_plans, None, set()), vehicles

    def load_simple_csv_solution(
        self, filepath: Path, instance: DARPInstance, fleet_sizing: bool = False
    ) -> Solution:
        """
        Load a solution from a simple CSV that contains only order of the requests to be served (no ridesharing allowed).
        The file should have two columns:
        - first column is plan (vehicle) index,
        - second column is request index from the instance. 
        No times in the file;
        """
        data = pd.read_csv(filepath)
        # Support 'plan'/'request' headers or first two columns by position
        plan_col = 'plan' if 'plan' in data.columns else data.columns[0]
        request_col = 'request' if 'request' in data.columns else data.columns[1]

        request_map = {r.index: r for r in instance.requests}
        config = instance.darp_instance_config
        travel_time_provider = instance.travel_time_provider
        travel_time_divider = getattr(config, 'travel_time_divider', 1) or 1
        instance_start_time = config.start_time

        vehicle_plans = []
        for plan_id, group in data.groupby(plan_col, sort=False):
            plan_id = int(plan_id)
            # In fleet sizing mode, do not generate any vehicle; use None
            if fleet_sizing:
                vehicle = None
            else:
                vehicle = instance.vehicles[plan_id]

            # Row order = order requests are served. Each request is pickup then dropoff
            request_order = group[request_col].astype(int).tolist()
            action_sequence = []
            for req_idx in request_order:
                action_sequence.append((req_idx, ActionType.PICKUP))
                action_sequence.append((req_idx, ActionType.DROP_OFF))

            if not action_sequence:
                continue

            first_req_idx, _ = action_sequence[0]
            first_request = request_map[first_req_idx]
            first_action = first_request.pickup_action
            current_position = (
                vehicle.initial_position if vehicle is not None else first_action.node
            )
            travel_time_to_first = travel_time_provider.get_travel_time(
                current_position, first_action.node
            ) / travel_time_divider

            if vehicle is not None and vehicle.operation_start is not None:
                current_time = vehicle.operation_start
            else:
                current_time = instance_start_time
            actions_data_list = []

            for req_idx, action_type in action_sequence:
                request = request_map[req_idx]
                action = request.pickup_action if action_type == ActionType.PICKUP else request.drop_off_action
                travel_time = travel_time_provider.get_travel_time(
                    current_position, action.node
                )
                travel_time = travel_time / travel_time_divider
                arrival_time = current_time = current_time + timedelta(seconds=int(travel_time))

                # wait for min time
                if action.min_time is not None and arrival_time < action.min_time:
                    current_time = action.min_time

                departure_time = current_time = current_time + timedelta(seconds=int(action.service_time))
                actions_data_list.append(ActionData(action, arrival_time, departure_time))
                current_position = action.node

            departure_datetime = actions_data_list[0].departure_time
            arrival_datetime = actions_data_list[-1].departure_time
            vh_plan = VehiclePlan(
                vehicle, actions_data_list, None, departure_datetime, arrival_datetime
            )
            vehicle_plans.append(vh_plan)

        return Solution(vehicle_plans, None, set())

    def _load_plan(
        self,
        json_data,
        use_virtual_vehicles: bool,
        vehicle_map: Dict[int, Vehicle],
        request_map: Dict[int, Request],
        fleet_sizing: bool = False,
    ) -> Tuple[VehiclePlan, int]:
        if fleet_sizing:
            v = json_data["vehicle"]
            vid = int(v.get("index", v.get("id", 0)))
            vehicle = Vehicle(vid, 0, 999, [], None, None)
        elif use_virtual_vehicles:
            vehicle = vehicle_map[0]
        else:
            # legacy name for id
            if 'index' in json_data["vehicle"]:
                vehicle = vehicle_map[json_data["vehicle"]["index"]]
            else:
                vehicle = vehicle_map[int(json_data["vehicle"]["id"])]
        actions_data_list = []

        # action data loading
        mismatch_actions_count = 0
        for action_data in json_data["actions"]:
            # time loading
            arrival_time = self.time_loader.load_time_field(action_data["arrival_time"])
            departure_time = self.time_loader.load_time_field(action_data["departure_time"])

            # Load action from dictionary
            action_from_solution = self._load_action_from_dict(action_data["action"], request_map)

            # get the action definition from instance data
            request = action_from_solution.request
            if action_from_solution.action_type == ActionType.PICKUP:
                action_from_instance = request.pickup_action
            else:
                action_from_instance = request.drop_off_action

            action_field_equals = self._action_fields_equals(action_from_instance, action_from_solution)
            if not action_field_equals:
                mismatch_actions_count += 1

            actions_data_list.append(ActionData(action_from_instance, arrival_time, departure_time))

        departure_datetime = self.time_loader.load_time_field(json_data["departure_time"])
        arrival_datetime = self.time_loader.load_time_field(json_data["arrival_time"])

        vh_plan = VehiclePlan(vehicle, actions_data_list, json_data["cost"], departure_datetime, arrival_datetime)
        return vh_plan, mismatch_actions_count

    def _load_action_from_dict(self, action_dict: Dict, request_map: Dict[int, Request]) -> Action:
        """
        Load an Action object from a dictionary representation.
        
        Args:
            action_dict: Dictionary containing action data
            request_map: Mapping from request index to Request object
            
        Returns:
            Action object created from the dictionary
        """
        # Get the request
        request = request_map[action_dict["request_index"]]
        
        # Determine action type
        action_type = ActionType.PICKUP if action_dict["type"] == "pickup" else ActionType.DROP_OFF
        
        # Get the node (position)
        node = request.pickup_action.node if action_type == ActionType.PICKUP else request.drop_off_action.node
        
        # Load times using TimeLoader
        min_time = None
        if "min_time" in action_dict:
            min_time = self.time_loader.load_time_field(action_dict["min_time"])
        
        max_time = None
        if "max_time" in action_dict:
            max_time = self.time_loader.load_time_field(action_dict["max_time"])
        
        # Get service time (default to 0 if not specified). The schema names the field
        # "service_duration"; "service_time" is accepted for backward compatibility.
        service_time = action_dict.get("service_duration", action_dict.get("service_time", 0))
        
        # Create Action object
        action_id = request.pickup_action.id if action_type == ActionType.PICKUP else request.drop_off_action.id
        
        return Action(
            action_id=action_id,
            node=node,
            min_time=min_time,
            max_time=max_time,
            action_type=action_type,
            request=request,
            service_time=service_time
        )

    def _action_fields_equals(self, action_from_instance: Action, action_from_solution: Action) -> bool:
        correct = True

        # min time constraint (has meaning only for pickup actions)
        if action_from_instance.action_type == ActionType.PICKUP and action_from_solution.min_time is not None:
            if action_from_solution.min_time != action_from_instance.min_time:
                logging.warning(
                    "%s min time mismatch: Action from instance: %s, action from solution: %s",
                    _get_action_info_string_from_action(action_from_solution),
                    action_from_instance.min_time,
                    action_from_solution.min_time
                )
                self._increment_error(LoadingError.ACTION_MIN_TIME_MISMATCH)
                correct = False

        # max time constraint
        if action_from_solution.max_time is not None:
            if action_from_solution.max_time != action_from_instance.max_time:
                logging.warning(
                    "%s max time mismatch: Action from instance: %s, action from solution: %s",
                    _get_action_info_string_from_action(action_from_solution),
                    action_from_instance.max_time,
                    action_from_solution.max_time
                )
                self._increment_error(LoadingError.ACTION_MAX_TIME_MISMATCH)
                correct = False

        # action position (int for matrix/grid, Coordinate for Cordeau)
        if not _nodes_equal(action_from_solution.node, action_from_instance.node):
            logging.warning(
                "%s position mismatch: Action from instance: %s, action from solution: %s",
                _get_action_info_string_from_action(action_from_solution),
                _node_repr(action_from_instance.node),
                _node_repr(action_from_solution.node)
            )
            self._increment_error(LoadingError.ACTION_POSITION_MISMATCH)
            correct = False

        return correct

    def _load_action_from_csv(self, action_row: pd.Series, simulation_start_time: datetime,
                             request_map: Dict[int, Request]) -> Optional[ActionData]:
        action_type_str = action_row['action']

        if action_type_str not in ["P", "D"]:
            return None

        request_id = action_row['request_id']
        node = int(action_row['node_id'])

        # time loading
        arrival_time = None
        departure_time = simulation_start_time + timedelta(seconds=int(action_row['time']))

        # mapping to request
        request = request_map[request_id]

        # get the action definition from instance data
        action_type = ActionType.PICKUP if action_type_str == "P" else ActionType.DROP_OFF
        if action_type == ActionType.PICKUP:
            action_from_instance = request.pickup_action
        else:
            action_from_instance = request.drop_off_action

        if not _nodes_equal(action_from_instance.node, node):
            logging.warning(
                "Node mismatch for request %d, action %d: Action from instance: %s, action from solution: %s",
                request_id,
                action_row.name - 1,
                _node_repr(action_from_instance.node),
                _node_repr(node)
            )
            self._increment_error(LoadingError.NODE_MISMATCH)

        return ActionData(action_from_instance, arrival_time, departure_time)

    def _load_plan_from_csv(
        self,
        plan_data: pd.DataFrame,
        request_map: Dict[int, Request],
        vehicle_map: Dict[int, Vehicle],
        simulation_start_time: datetime
    ) -> VehiclePlan:
        vehicle = vehicle_map[plan_data.name]

        # action data loading
        actions_data_list = []
        for _, row in plan_data.iterrows():
            action_data = self._load_action_from_csv(row, simulation_start_time, request_map)
            if action_data is not None:
                actions_data_list.append(action_data)

        if len(actions_data_list) == 0:
            logging.debug("Empty plan for vehicle %d", vehicle.index)
            return None

        departure_datetime = actions_data_list[0].departure_time
        arrival_datetime = actions_data_list[-1].departure_time

        vh_plan = VehiclePlan(vehicle, actions_data_list, None, departure_datetime, arrival_datetime)
        return vh_plan




# Replaced by method in SolutionLoader class


def _load_vehicle_from_csv(vehicle_row: pd.Series, simulation_start_time: datetime, vehicle_capacity: int) -> Vehicle:
    operation_start = simulation_start_time + timedelta(seconds=int(vehicle_row['time']))
    return Vehicle(int(vehicle_row['vehicle_id']), int(vehicle_row['node_id']), vehicle_capacity, operation_start=operation_start)


# Replaced by method in SolutionLoader class


def load_solution(
    filepath: Path, instance: DARPInstance, time_loader: TimeLoader, fleet_sizing: bool = False
) -> Solution:
    """Load a solution from a file using the SolutionLoader class

    Args:
        filepath: Path to the solution file
        instance: DARP instance
        time_loader: TimeLoader instance for parsing time values
        fleet_sizing: If True, vehicles are not loaded from instance; placeholder vehicles are built from the solution file.

    Returns:
        Solution object
    """
    solution_loader = SolutionLoader(time_loader=time_loader)
    return solution_loader.load_solution(filepath, instance, fleet_sizing)


def _prepare_maps(instance: DARPInstance) -> Tuple[Dict[int, Request], Dict[int, Vehicle]]:
    request_map = dict()
    for request in instance.requests:
        request_map[request.index] = request

    # vehicles
    vehicle_map = dict()
    if instance.darp_instance_config.virtual_vehicles:
        vehicle_map[0] = instance.vehicles[0]
    else:
        for vehicle in instance.vehicles:
            vehicle_map[vehicle.index] = vehicle

    return request_map, vehicle_map


def _get_action_info_string_from_action(action: Action) -> str:
    """Get a string representation of action information for logging."""
    type_string = "Pickup" if action.action_type == ActionType.PICKUP else "Drop-off"
    return f"{type_string} action for request {action.request.index}"


def _get_action_info_string(action):
    type_string = "Pickup" if action["type"] == "pickup" else "Drop-off"
    return f"{type_string} action for request {action['request_index']}"


# Replaced by method in SolutionLoader class


# Replaced by method in SolutionLoader class


def load_plan(filepath: str, instance: DARPInstance, time_loader: TimeLoader) -> Tuple[VehiclePlan, int]:
    json_data = load_json(filepath)
    request_map, vehicle_map = _prepare_maps(instance)

    solution_loader = SolutionLoader(time_loader=time_loader)
    vp, mismatch_count = solution_loader._load_plan(json_data, instance.darp_instance_config.virtual_vehicles, vehicle_map, request_map)

    return vp, mismatch_count


# Replaced by method in SolutionLoader class


# Replaced by method in SolutionLoader class
