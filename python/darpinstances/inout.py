import os
import json
import logging
import csv
import pkgutil
import numpy as np
import h5py
from pathlib import Path

from typing import Tuple, Dict, Iterable

import darpbenchmark.log
from darpinstances.instance import DARPInstance, Action, ActionType, Vehicle, VirtualVehicle, Request
from darpinstances.vehicle_plan import ActionData, VehiclePlan
from darpinstances.solution import Solution


def load_csv(filepath: str, delimiter: str = ",") -> Iterable:
	logging.info("Loading csv file from:  %s", os.path.realpath(filepath))
	f = open(filepath, "r")
	return csv.reader(f, delimiter=delimiter)


def load_json(filepath: str):
	logging.info("Loading json file from: {}".format(os.path.realpath(filepath)))
	return json.load(open(filepath, encoding="utf-8"))


def load_resource(package_path: str, filename: str) -> str:
	try:
		resource = pkgutil.get_data(package_path, filename)
		if resource:
			content = resource.decode("utf-8")
		else:
			logging.critical("File %s cannot be loaded from resource path: %s", filename, package_path)
			raise Exception("File cannot be loaded", "{}/{}".format(package_path, filename))

		return content
	except FileNotFoundError as e:
		logging.critical("File %s cannot be found in resource path: %s", filename, package_path)
		raise Exception("File not found", "{}/{}".format(package_path, filename))


def get_resource_absolute_path(package_path: str, filename: str) -> str:
	try:
		package = pkgutil.get_loader(package_path)
		return f"{Path(package.get_filename()).parent}/{filename}"

	except FileNotFoundError as e:
		logging.critical("Package %s does not exist", package_path)
		raise Exception(f"Package {package_path} does not exist")


def load_solution(filepath: str, instance: DARPInstance) -> Solution:

	json_data = load_json(filepath)

	request_map, vehicle_map = _prepare_maps(instance)

	vehicle_plans = []
	for plan in json_data["plans"]:
		vehicle_plans.append(_load_plan(plan, instance, vehicle_map, request_map))
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
		instance: DARPInstance,
		vehicle_map: Dict[int,Vehicle],
		request_map: Dict[int,Request]
) -> VehiclePlan:
	if instance.darp_instance_config.virtual_vehicles:
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

	vp = _load_plan(json_data, instance, vehicle_map, request_map)

	return vp


def check_file_exists(path: str, raise_ex: bool = True) -> bool:
	if not os.path.exists(path) and not os.path.isdir(path):
		if raise_ex:
			abs_path = os.path.abspath(path)
			if path == abs_path:
				raise Exception(f"file '{path}' does not exists!")
			else:
				raise Exception(f"file '{path}' does not exists! (absolute path: {abs_path})")
		else:
			return False
	return True


def get_test_resource(file_name: str) -> Path:
	python_root_dir = Path(__file__).parent.parent
	benchmark_root_dir = python_root_dir.parent
	test_resource_dir = benchmark_root_dir / "data" / "test_resources"
	return test_resource_dir / file_name


def load_hdf(file_path: str) -> np.ndarray:
	logging.info("Loading data from %s", os.path.abspath(file_path))
	with h5py.File(file_path, "r") as f:
		a_group_key = list(f.keys())[0]
		dm_ar = f[a_group_key][()]
		return dm_ar
