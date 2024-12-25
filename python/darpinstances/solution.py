import logging
from typing import List, Optional, Set, Tuple, Dict
from datetime import datetime

from darpinstances.inout import load_json
from darpinstances.instance import DARPInstance, Request, Vehicle
from darpinstances.instance_generation.instance_objects import ActionType, Action
from darpinstances.vehicle_plan import VehiclePlan, ActionData


class Solution:
    def __init__(self, vehicle_plans: List[VehiclePlan], cost: int, dropped_requests=Optional[Set[int]], feasible=True):
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
        return 'solution: cost {}.\nPlans: {}.' \
            .format(self.cost, '\n'.join([str(p) for p in self.vehicle_plans]))

def _load_datetime(string: str):
    return datetime.strptime(string, '%Y-%m-%d %H:%M:%S')

def load_solution(filepath: str, instance: DARPInstance) -> Solution:
    json_data = load_json(filepath)

    # handle infesible solutions
    if "feasible" in json_data and json_data["feasible"] == False:
        return Solution.make_infeasible()

    request_map, vehicle_map = _prepare_maps(instance)

    vehicle_plans = []
    total_missmatch_actions = 0
    for json_plan in json_data["plans"]:
        plan, mismatch_actions_count = _load_plan(json_plan, instance.darp_instance_config.virtual_vehicles, vehicle_map, request_map)
        vehicle_plans.append(plan)
        total_missmatch_actions += mismatch_actions_count

    if total_missmatch_actions > 0:
        raise Exception(f"Mismatch in actions found in the solution file. Total mismatch count: {total_missmatch_actions}")

    dropped_requests = set()
    for request in json_data["dropped_requests"]:
        dropped_requests.add(int(request["id"]))
    return Solution(vehicle_plans, json_data["cost"], dropped_requests)


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
            logging.warning("%s min time mismatch: Action from instance: %s, action from solution: %s",
                            _get_action_info_string(action), action_from_instance.min_time, action["min_time"])
            correct = False

    # max time constraint
    if "max_time" in action:
        max_time_solution = _load_datetime(action["max_time"])
        if max_time_solution != action_from_instance.max_time:
            logging.warning("%s max time mismatch: Action from instance: %s, action from solution: %s",
                            _get_action_info_string(action), action_from_instance.max_time, action["max_time"])
            correct = False

    # action position
    if "position" in action and action["position"] != action_from_instance.node.get_idx():
        logging.warning("%s position mismatch: Action from instance: %s, action from solution: %s",
                        _get_action_info_string(action), action_from_instance.node.get_idx(), action["position"])
        correct = False

    return correct


def _load_plan(
        json_data,
        use_virtual_vehicles: bool,
        vehicle_map: Dict[int, Vehicle],
        request_map: Dict[int, Request]
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
            arrival_time = datetime.utcfromtimestamp(arrival_time_val)
            departure_time = datetime.utcfromtimestamp(departure_time_val)
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
        departure_datetime = datetime.utcfromtimestamp(json_data["departure_time"])
        arrival_datetime = datetime.utcfromtimestamp(json_data["arrival_time"])
    else:
        departure_datetime = _load_datetime(json_data["departure_time"])
        arrival_datetime = _load_datetime(json_data["arrival_time"])

    vh_plan = VehiclePlan(
        vehicle, json_data["cost"], actions_data_list, departure_datetime, arrival_datetime)
    return vh_plan, mismatch_actions_count


def load_plan(filepath: str, instance: DARPInstance) -> VehiclePlan:
    json_data = load_json(filepath)

    request_map, vehicle_map = _prepare_maps(instance)

    vp = _load_plan(json_data, instance.darp_instance_config.virtual_vehicles, vehicle_map, request_map)

    return vp
