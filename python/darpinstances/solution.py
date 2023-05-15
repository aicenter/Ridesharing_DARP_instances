from typing import List, Optional, Set, Tuple, Dict

from darpinstances.inout import load_json
from darpinstances.instance import DARPInstance, Request, Vehicle
from darpinstances.instance_generation.instance_objects import ActionType
from darpinstances.vehicle_plan import VehiclePlan, ActionData


class Solution:
    def __init__(self, vehicle_plans: List[VehiclePlan], cost: int, dropped_requests=Optional[Set[int]]):
        """
        Constructor
        :param vehicle_plans: List of vehicle plans
        :param cost: Total cost
        :param dropped_requests: Set of dropped requests' indices
        """
        self.vehicle_plans = vehicle_plans
        self.cost = cost
        if dropped_requests is None:
            self.dropped_requests = []
        else:
            self.dropped_requests = dropped_requests

    def __str__(self):
        return 'solution: cost {}.\nPlans: {}.' \
            .format(self.cost, '\n'.join([str(p) for p in self.vehicle_plans]))


def load_solution(filepath: str, instance: DARPInstance) -> Solution:
    json_data = load_json(filepath)

    request_map, vehicle_map = _prepare_maps(instance)

    vehicle_plans = []
    for plan in json_data["plans"]:
        vehicle_plans.append(_load_plan(plan, instance.darp_instance_config.virtual_vehicles, vehicle_map, request_map))
    dropped_requests = set()
    for request in json_data["dropped_requests"]:
        dropped_requests.add(int(request["index"]))
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


def _load_plan(
        json_data,
        use_virtual_vehicles: bool,
        vehicle_map: Dict[int, Vehicle],
        request_map: Dict[int, Request]
) -> VehiclePlan:
    if use_virtual_vehicles:
        vehicle = vehicle_map[0]
    else:
        vehicle = vehicle_map[json_data["vehicle"]["index"]]
    actions_data_list = []
    for action_data in json_data["actions"]:
        arrival_time = action_data["arrival_time"]
        departure_time = action_data["departure_time"]
        action = action_data["action"]

        action_inst = ""
        action_type = ActionType.PICKUP if action["type"] == "pickup" else ActionType.DROP_OFF
        if action_type == action_type.PICKUP:
            action_inst = request_map[action["request_index"]].pickup_action
        else:
            action_inst = request_map[action["request_index"]].drop_off_action

        actions_data_list.append(ActionData(action_inst, arrival_time, departure_time))

    vh_plan = VehiclePlan(
        vehicle, json_data["cost"], actions_data_list, int(json_data["departure_time"]), int(json_data["arrival_time"]))
    return vh_plan


def load_plan(filepath: str, instance: DARPInstance) -> VehiclePlan:
    json_data = load_json(filepath)

    request_map, vehicle_map = _prepare_maps(instance)

    vp = _load_plan(json_data, instance.darp_instance_config.virtual_vehicles, vehicle_map, request_map)

    return vp
