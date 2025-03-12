import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set, Tuple, Dict, Iterable
import pandas as pd
from pandera.typing import Series

from darpinstances.inout import load_json
from darpinstances.instance import DARPInstance, Request, Vehicle
from darpinstances.instance_generation.instance_objects import ActionType, Action
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


def _load_datetime(string: str):
    return datetime.strptime(string, '%Y-%m-%d %H:%M:%S')


def load_json_solution(filepath, use_virtual_vehicles, request_map, vehicle_map):
    json_data = load_json(filepath)

    # handle infesible solutions
    if "feasible" in json_data and json_data["feasible"] == False:
        return Solution.make_infeasible()

    vehicle_plans = []
    total_missmatch_actions = 0
    for json_plan in json_data["plans"]:
        plan, mismatch_actions_count = _load_plan(json_plan, use_virtual_vehicles, vehicle_map, request_map)
        vehicle_plans.append(plan)
        total_missmatch_actions += mismatch_actions_count

    if total_missmatch_actions > 0:
        raise Exception(
            f"Mismatch in actions found in the solution file. Total mismatch count: {total_missmatch_actions}"
        )

    dropped_requests = set()
    for request in json_data["dropped_requests"]:
        dropped_requests.add(int(request["id"]))
    return Solution(vehicle_plans, json_data["cost"], dropped_requests)


def _load_vehicle_from_csv(vehicle_row: pd.Series, simulation_start_time: datetime, vehicle_capacity: int) -> Vehicle:
    operation_start = simulation_start_time + timedelta(seconds=int(vehicle_row['time']))
    return Vehicle(vehicle_row['vehicle_id'], vehicle_row['node_id'], vehicle_capacity, operation_start=operation_start)


def load_csv_solution(filepath, request_map, simulation_start_time: datetime, vehicle_capacity: int) \
    -> Tuple[Solution, Series[Vehicle]]:
    data = pd.read_csv(filepath)

    # vehicle_plans = []

    vehicles = data[data['action'] == 'E'][['vehicle_id', 'node_id', 'time']].apply(
        _load_vehicle_from_csv, axis=1, args=(simulation_start_time, vehicle_capacity)
    )

    vehicle_map = dict()
    for vehicle in vehicles:
        vehicle_map[vehicle.index] = vehicle

    vehicle_plans = data.groupby("vehicle_id").apply(
        _load_plan_from_csv, axis=1, args=(request_map, vehicle_map, simulation_start_time)
    )

    # for json_plan in json_data["plans"]:
    #     plan, mismatch_actions_count = _load_plan(json_plan, use_virtual_vehicles, vehicle_map,  request_map)
    #     vehicle_plans.append(plan)

    return Solution(vehicle_plans, None, set()), vehicles


def load_solution(filepath: Path, instance: DARPInstance) -> Solution:
    request_map, vehicle_map = _prepare_maps(instance)

    logging.info(f"Loading solution from {filepath}")

    if filepath.suffix == '.json':
        return load_json_solution(filepath, instance.darp_instance_config.virtual_vehicles, request_map, vehicle_map)
    else:
        solution, vehicles = load_csv_solution(
            filepath,
            request_map,
            instance.darp_instance_config.start_time,
            instance.darp_instance_config.vehicle_capacity
        )
        instance.vehicles = vehicles
        return solution


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


def _get_action_info_string(action):
    type_string = "Pickup" if action["type"] == "pickup" else "Drop-off"
    return f"{type_string} action for request {action['request_index']}"


def _action_fields_equals(action_from_instance: Action, action: Dict) -> bool:
    correct = True

    # min time constraint (has meaning only for pickup actions)
    if action_from_instance.action_type == ActionType.PICKUP and "min_time" in action:
        min_time_solution = _load_datetime(action["min_time"])
        if min_time_solution != action_from_instance.min_time:
            logging.warning(
                "%s min time mismatch: Action from instance: %s, action from solution: %s",
                _get_action_info_string(action),
                action_from_instance.min_time,
                action["min_time"]
            )
            correct = False

    # max time constraint
    if "max_time" in action:
        max_time_solution = _load_datetime(action["max_time"])
        if max_time_solution != action_from_instance.max_time:
            logging.warning(
                "%s max time mismatch: Action from instance: %s, action from solution: %s",
                _get_action_info_string(action),
                action_from_instance.max_time,
                action["max_time"]
            )
            correct = False

    # action position
    if "position" in action and action["position"] != action_from_instance.node.get_idx():
        logging.warning(
            "%s position mismatch: Action from instance: %s, action from solution: %s",
            _get_action_info_string(action),
            action_from_instance.node.get_idx(),
            action["position"]
        )
        correct = False

    return correct


def _load_plan(
    json_data, use_virtual_vehicles: bool, vehicle_map: Dict[int, Vehicle], request_map: Dict[int, Request]
) -> Tuple[VehiclePlan, int]:
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
        action = action_data["action"]

        # time loading
        arrival_time_val = action_data["arrival_time"]
        departure_time_val = action_data["departure_time"]
        if isinstance(arrival_time_val, int):
            arrival_time = datetime.fromtimestamp(arrival_time_val)
            departure_time = datetime.fromtimestamp(departure_time_val)
        else:
            arrival_time = _load_datetime(arrival_time_val)
            departure_time = _load_datetime(departure_time_val)

        # mapping to request
        request = request_map[action["request_index"]]

        # get the action definition from instance data
        action_type = ActionType.PICKUP if action["type"] == "pickup" else ActionType.DROP_OFF
        if action_type == action_type.PICKUP:
            action_from_instance = request.pickup_action
        else:
            action_from_instance = request.drop_off_action

        action_field_equals = _action_fields_equals(action_from_instance, action)
        if not action_field_equals:
            mismatch_actions_count += 1

        actions_data_list.append(ActionData(action_from_instance, arrival_time, departure_time))

    if isinstance(json_data["departure_time"], int):
        departure_datetime = datetime.fromtimestamp(json_data["departure_time"])
        arrival_datetime = datetime.fromtimestamp(json_data["arrival_time"])
    else:
        departure_datetime = _load_datetime(json_data["departure_time"])
        arrival_datetime = _load_datetime(json_data["arrival_time"])

    vh_plan = VehiclePlan(
        vehicle, json_data["cost"], actions_data_list, departure_datetime, arrival_datetime
    )
    return vh_plan, mismatch_actions_count


def load_plan(filepath: str, instance: DARPInstance) -> Tuple[VehiclePlan, int]:
    json_data = load_json(filepath)

    request_map, vehicle_map = _prepare_maps(instance)

    vp = _load_plan(json_data, instance.darp_instance_config.virtual_vehicles, vehicle_map, request_map)

    return vp


def _load_action_from_csv(
    # action_index: int,
    # time: int,
    # action_type_str: str,
    # node: int,
    # request_id: int,
    action_row: pd.Series, simulation_start_time: datetime, request_map: Dict[int, Request]
) -> Optional[ActionData]:
    action_type_str = action_row['action']

    if action_type_str not in ["P", "D"]:
        return None

    request_id = action_row['request_id']
    node = action_row['node']

    # time loading
    arrival_time = simulation_start_time + timedelta(seconds=int(action_row['time']))
    departure_time = arrival_time

    # mapping to request
    request = request_map[request_id]

    # get the action definition from instance data
    action_type = ActionType.PICKUP if action_type_str == "P" else ActionType.DROP_OFF
    if action_type == action_type.PICKUP:
        action_from_instance = request.pickup_action
    else:
        action_from_instance = request.drop_off_action

    if action_from_instance.node.get_idx() != node:
        logging.warning(
            "Node mismatch for request %, action %: Action from instance: %s, action from solution: %s",
            request_id,
            action_row.index - 1,
            action_from_instance.node.get_idx(),
            node
            )

    return ActionData(action_from_instance, arrival_time, departure_time)


def _load_plan_from_csv(
    plan_data: pd.DataFrame,
    vehicle_map: Dict[int, Vehicle],
    request_map: Dict[int, Request],
    simulation_start_time: datetime
) -> VehiclePlan:
    vehicle = vehicle_map[plan_data.iloc[0]["vehicle_id"]]

    # action data loading
    actions_data_list = plan_data.apply(
        _load_action_from_csv,
        axis=1,
        args=(simulation_start_time, request_map)
    ).notnull()

    # actions_data_list = [_load_action_from_csv(action_index, time, action_type_str, node, request_id, simulation_start_time,
    # request_map for action_index, time, action_type_str, node, request_id in zip

    departure_datetime = actions_data_list[0].arrival_time
    arrival_datetime = actions_data_list[-1].departure_time

    vh_plan = VehiclePlan(
        vehicle, None, actions_data_list, departure_datetime, arrival_datetime
    )
    return vh_plan
