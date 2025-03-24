import os
import re

import darpinstances.instance

from typing import List, Tuple, Dict

from darpinstances.instance import DARPInstance
from darpinstances.instance_objects import Request, ActionType, Vehicle
from darpinstances.solution import Solution
from darpinstances.vehicle_plan import VehiclePlan


SOLUTION_REGEX_STRING = r"^([0-9]+) +D: +([0-9.]+) Q: +([0-9.]+) W: +([0-9.]+) T: +([0-9.]+) +[0-9]+ +\(b:([0-9.]+); +t:[0-9.]+; +q:[0-9.]+\)((?: +[0-9]+ +\(w:[0-9.]+ +a:[0-9.]+; +t:[0-9.]+; q:[0-9.]+\))*)"
ACTION_REGEX_STRING = r" +([0-9]+) +\(w:([0-9.]+) +a:([0-9.]+); +t:([0-9.]+); q:([0-9.])+\)"
SOLUTION_REGEX = re.compile(SOLUTION_REGEX_STRING)
ACTION_REGEX = re.compile(ACTION_REGEX_STRING)


class CordeauNode(darpinstances.instance.Coordinate):
	def get_x(self) -> float:
		return self.x

	def get_y(self) -> float:
		return self.y

	def __init__(self, x: float, y: float):
		self.x = x
		self.y = y


def load(filepath: str) -> DARPInstance:
	print("Reading Cordeau DARP instance from: {}".format(os.path.realpath(filepath)))

	with open(filepath, "r", encoding="utf-8") as infile:
		first_line = infile.readline().split()
		num_vehicles: int = int(first_line[0])
		num_requests: int = int(first_line[1])
		max_route_duration: int = int(first_line[2])
		vehicle_capacity: int = int(first_line[3])
		max_ride_time: int = int(first_line[4])

		second_line = infile.readline().split()
		depot_x: float = float(second_line[1])
		depot_y: float = float(second_line[2])

		vehicles = []
		depot_node = CordeauNode(depot_x, depot_y)

		for index in range(num_vehicles):
			vehicles.append(darpinstances.instance.Vehicle(index, depot_node, vehicle_capacity))

		origin_actions: List[Tuple[int, CordeauNode, int, int, int]] = []

		requests: List[Request] = []

		travel_time_provider = darpinstances.instance.EuclideanTravelTimeProvider(60)

		line_string = infile.readline()
		counter = 0
		index = 0
		while (line_string):
			line = line_string.split()
			id: int = int(line[0])
			x: float = float(line[1])
			y: float = float(line[2])
			service_time: int = int(line[3])
			origin: int = int(line[4])
			min_time: int = int(line[5])
			max_time: int = int(line[6])
			node = CordeauNode(x, y)
			if origin == 1:
				origin_actions.append((id, node, min_time * 60, max_time * 60, service_time * 60))
			else:
				min_travel_time = travel_time_provider.get_travel_time(origin_actions[counter][1], node)
				requests.append(Request(index, origin_actions[counter][0], origin_actions[counter][1],
										origin_actions[counter][2], origin_actions[counter][3], id,
										node, min_time * 60, max_time * 60, min_travel_time,
										origin_actions[counter][4], service_time * 60))
				counter += 1
				index += 1

			line_string = infile.readline()

		return DARPInstance(requests, vehicles, travel_time_provider, max_route_duration * 60, max_ride_time * 60)


def load_cordeau_solution(filepath: str, vehicle_map: Dict[int, Vehicle] , request_map: Dict[int, Request]) -> Solution:
	print("Reading Cordeau DARP solution from: {}".format(os.path.realpath(filepath)))

	with open(filepath, "r", encoding="utf-8") as infile:
		total_cost = float(infile.readline())

		vehicle_plans = []
		line_string = infile.readline()
		while (line_string):
			match = SOLUTION_REGEX.match(line_string)
			if(match):
				vehicle_index = int(match.group(1)) - 1
				total_plan_time = float(match.group(2))
				max_used_capacity = float(match.group(3))
				average_wait_time = float(match.group(4))
				average_transit_time = float(match.group(5))
				departure_time = float(match.group(6))
				actions_string = match.group(7)



				# parse actions
				action_matches: List[Tuple[str]] = ACTION_REGEX.findall(actions_string)
				actions = []
				# picked_request_indexes = set()
				total_wait_time = 0
				for action_match in action_matches[0:-1]:
					action_index = int(action_match[0])
					wait_time = float(action_match[1])
					action_time = float(action_match[2])
					passenger_time = float(action_match[3])
					occupancy = int(action_match[4])

					action_type = ActionType.PICKUP if action_index <= len(request_map) else ActionType.DROP_OFF
					if action_type == action_type.PICKUP:
						actions.append(request_map[action_index - 1].pickup_action)
					else:
						actions.append(request_map[action_index - len(request_map) - 1].drop_off_action)

					total_wait_time += wait_time

				vehicle = vehicle_map[vehicle_index]

				# plan cost computation
				total_service_time = 0
				for action in actions:
					total_service_time += action.service_time
				plan_cost_with_service_time = total_plan_time - total_wait_time

				vh_plan = VehiclePlan(vehicle, actions, round(plan_cost_with_service_time * 60) - total_service_time)
				vehicle_plans.append(vh_plan)
			line_string = infile.readline()

		return Solution(vehicle_plans, int(round(total_cost * 60)))
