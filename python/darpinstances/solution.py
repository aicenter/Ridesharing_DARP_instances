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


    def load_solution(self, filepath: Path, instance: DARPInstance) -> Solution:
        request_map, vehicle_map = _prepare_maps(instance)

        logging.info(f"Loading solution from {filepath}")

        if filepath.suffix == '.json':
            return self.load_json_solution(filepath, instance.darp_instance_config.virtual_vehicles, request_map, vehicle_map)
        else:
            solution, vehicles = self.load_csv_solution(
                filepath,
                request_map,
                instance.darp_instance_config.start_time,
                instance.darp_instance_config.vehicle_capacity
            )
            instance.vehicles = vehicles
            return solution

    def load_json_solution(self, filepath, use_virtual_vehicles, request_map, vehicle_map):
        json_data = load_json(filepath)

        # handle infesible solutions
        if "feasible" in json_data and json_data["feasible"] == False:
            return Solution.make_infeasible()

        vehicle_plans = []
        total_missmatch_actions = 0
        for json_plan in json_data["plans"]:
            plan, mismatch_actions_count = self._load_plan(json_plan, use_virtual_vehicles, vehicle_map, request_map)
            vehicle_plans.append(plan)
            total_missmatch_actions += mismatch_actions_count

        if total_missmatch_actions > 0:
            logging.warning(f"Mismatch in actions found in the solution file. Total mismatch count: {total_missmatch_actions}")
            self._increment_error()

        dropped_requests = set()
        for request in json_data["dropped_requests"]:
            dropped_requests.add(int(request["id"]))
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

    def _load_plan(self, json_data, use_virtual_vehicles: bool, vehicle_map: Dict[int, Vehicle],
                  request_map: Dict[int, Request]) -> Tuple[VehiclePlan, int]:
        if use_virtual_vehicles:
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
        
        # Get service time (default to 0 if not specified)
        service_time = action_dict.get("service_time", 0)
        
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

        # action position
        if action_from_solution.node.get_idx() != action_from_instance.node.get_idx():
            logging.warning(
                "%s position mismatch: Action from instance: %s, action from solution: %s",
                _get_action_info_string_from_action(action_from_solution),
                action_from_instance.node.get_idx(),
                action_from_solution.node.get_idx()
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
        node = action_row['node_id']

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

        if action_from_instance.node != node:
            logging.warning(
                "Node mismatch for request %d, action %d: Action from instance: %d, action from solution: %d",
                request_id,
                action_row.name - 1,
                action_from_instance.node,
                node
            )
            self._increment_error(LoadingError.NODE_MISMATCH)

        return ActionData(action_from_instance, arrival_time, departure_time)

    def _load_plan_from_csv(self, plan_data: pd.DataFrame, request_map: Dict[int, Request],
                           vehicle_map: Dict[int, Vehicle], simulation_start_time: datetime) -> VehiclePlan:
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
    return Vehicle(vehicle_row['vehicle_id'], vehicle_row['node_id'], vehicle_capacity, operation_start=operation_start)


# Replaced by method in SolutionLoader class


def load_solution(filepath: Path, instance: DARPInstance, time_loader: TimeLoader) -> Solution:
    """Load a solution from a file using the SolutionLoader class

    Args:
        filepath: Path to the solution file
        instance: DARP instance
        time_loader: TimeLoader instance for parsing time values

    Returns:
        Solution object
    """
    solution_loader = SolutionLoader(time_loader=time_loader)
    return solution_loader.load_solution(filepath, instance)


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
