import argparse
import copy
import logging
import os
import os.path
from datetime import timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Tuple, Set, Optional, Dict, List

import pandas as pd

import darpinstances.experiments
import darpinstances.inout
import darpinstances.instance
from darpinstances.cordeau_benchmark import load as load_cordeau
from darpinstances.inout import check_file_exists
from darpinstances.instance import DARPInstance, TravelTimeProvider
from darpinstances.instance_objects import Request, Action, ActionType
from darpinstances.solution import VehiclePlan, Solution


# darp_folder_path = Path("C:\Google Drive/AIC Experiment Data\DARP")
# darp_folder_path = Path(r"D:\Google Drive AIC/AIC Experiment Data\DARP")
# darp_folder_path = Path(r"D:\Google Drive Citya\Bezba")
#
# instance_path = None
# # solution_file_path = darp_folder_path / r"final\Results\DC\start_18-00\duration_15_min\max_delay_10_min\halns-vga/config.yaml-solution.json"
# solution_file_path = darp_folder_path / r"fexperiments\2023-08-17-not_canceled\solutions/solution_2023-08-17_00-00-00.json"

# test HALNS instance
# instance_path = darp_folder_path / r'final/Instances/Chicago/instances/start_18-00/duration_05_min/max_delay_03_min/config.yaml'
# instance_path = darp_folder_path / r'final/Instances/DC/instances/start_18-00/duration_15_min/max_delay_10_min/config.yaml'
# solution_file_path = darp_folder_path / r"test/config.yaml-solution.json"


class Failure(Enum):
    PLAN_DEPARTURE_TIME = auto()


class SolutionChecker:
    def __init__(self, max_error_count: int = 10):
        self.error_count = 0
        self.max_error_count = max_error_count

    def _increment_error(self):
        self.error_count += 1
        if self.error_count > self.max_error_count:
            raise RuntimeError(f"Error count ({self.error_count}) exceeded maximum allowed errors ({self.max_error_count})")

    def check_plan(
        self,
        plan: VehiclePlan,
        plan_counter: int,
        instance: DARPInstance,
        used_vehicles: set,
        failures: Dict[Failure, int]
    ) -> Tuple[int, bool, Set[Request]]:
        plan_ok = True
        cost = 0.0

        if instance.darp_instance_config.start_time and plan.departure_time < instance.darp_instance_config.start_time:
            plan_ok = False
            failures[Failure.PLAN_DEPARTURE_TIME] += 1
            print(
                "[{}. plan]: departure time {} is smaller then the instance start time ({})".format(
                    plan_counter,
                    plan.departure_time,
                    instance.darp_instance_config.start_time
                )
            )
            self._increment_error()

        time = plan.departure_time
        free_capacity = plan.vehicle.capacity
        previous_action: Action = None
        onboard_requests = set()
        departure_times = dict()
        vehicle_index = plan.vehicle.index
        travel_time_provider = instance.travel_time_provider
        served_requests = set()
        vehicle_configurations = copy.deepcopy(plan.vehicle.configurations)
        used_equipment = []
        min_pause_length = instance.darp_instance_config.min_pause_length * 60
        max_pause_interval = instance.darp_instance_config.max_pause_interval * 60
        driving_start = time

        if not instance.darp_instance_config.virtual_vehicles:
            if vehicle_index in used_vehicles:
                print("[{}. plan]: Vehicle {} already used".format(plan_counter, vehicle_index))
                plan_ok = False
                self._increment_error()
            used_vehicles.add(vehicle_index)

        # operation time check
        operation_start = plan.vehicle.operation_start
        operation_end = plan.vehicle.operation_end
        if (operation_start and (plan.departure_time < operation_start)):
            print(
                "{} plan starts at {}. operation starts at {}, plan should not start before operation".format(
                    plan_counter,
                    plan.departure_time,
                    operation_start
                )
            )
            plan_ok = False
            self._increment_error()
        if (operation_end and (plan.arrival_time > operation_end)):
            print(
                "{} plan ends at {}. operation ends at {}, plan should not end after operation".format(
                    plan_counter,
                    plan.arrival_time,
                    operation_end
                )
            )
            plan_ok = False
            self._increment_error()

        travel_time_divider = instance.darp_instance_config.travel_time_divider

        for action_index, action_data in enumerate(plan.actions):
            action = action_data.action

            request = action.request
            is_drop_off = action.action_type == ActionType.DROP_OFF
            is_pickup = action.action_type == ActionType.PICKUP

            # onboard check
            if is_pickup:
                onboard_requests.add(request)
            else:
                if request in onboard_requests:
                    onboard_requests.remove(request)
                    served_requests.add(request)
                else:
                    print(
                        "[{}. plan] Request {} dropped off while not being picked up first.".format(
                            plan_counter, request.index
                        )
                    )
                    plan_ok = False
                    self._increment_error()

            if previous_action:
                travel_time = travel_time_provider.get_travel_time(previous_action.node, action_data.action.node)
            else:
                if instance.darp_instance_config.virtual_vehicles:
                    travel_time = plan.vehicle.time_to_start
                else:
                    travel_time = travel_time_provider.get_travel_time(
                        plan.vehicle.initial_position, action_data.action.node
                    )
            # adjust travel time if the provider is not in seconds
            travel_time = travel_time / travel_time_divider

            time += timedelta(seconds=int(travel_time))

            # arrival time check
            if action_data.arrival_time is not None:
                diff = action_data.arrival_time - time
                if diff > timedelta(seconds=1):
                    logging.warning(
                        f"[{plan_counter}. plan, {action_index + 1}. Action] Arrival time mismatch (expected {time}, "
                        f"was {action_data.arrival_time}) when handling request {action_data.action.request.index}"
                    )
                    self._increment_error()

            # max time check
            max_time = action_data.action.max_time + timedelta(seconds=instance.darp_instance_config.max_pickup_delay)
            if time > max_time:
                logging.warning(
                    "[{}. plan, {}. Action] Action max time exceeded ({} > {}) when handling request {}.".format(
                        plan_counter, action_index, time, action_data.action.max_time, action_data.action.request.index
                    )
                )
                plan_ok = False
                self._increment_error()

            # capacity check
            if not vehicle_configurations:
                if is_pickup:
                    if free_capacity == 0:
                        print(
                            "[{}. plan] Pickup action performed when vehicle was already full when handling request {}".format(
                                plan_counter, action_data.action.request.index
                            )
                        )
                        plan_ok = False
                        self._increment_error()
                    free_capacity -= 1
                else:
                    free_capacity += 1

            # equipment check
            matching_configurations = [config for config in vehicle_configurations if
                                       any(num in used_equipment for num in config)]
            available_configurations = copy.deepcopy(vehicle_configurations) if not used_equipment else copy.deepcopy(
                matching_configurations
            )
            for config in available_configurations:
                for item in used_equipment:
                    if item in config:
                        config.remove(item)

            equipment = action_data.action.request.equipment
            if equipment != 0:
                if is_pickup:
                    if not any(equipment in config for config in available_configurations):
                        print(
                            "Request {}, Equipment {} not available in vehicle equipment list. Vehicle: {}".format(
                                action_data.action.request.index,
                                equipment,
                                vehicle_index
                            )
                        )
                        plan_ok = False
                        self._increment_error()
                    used_equipment.append(equipment)
                elif is_drop_off:
                    used_equipment.remove(equipment)

            cost += travel_time

            # vehicle id check
            if action_data.action.request.required_vehicle_id is not None:
                if action_data.action.request.required_vehicle_id != vehicle_index:
                    logging.warning("Request {} is not for vehicle {}.".format(action_data.action.request.index, vehicle_index))
                    plan_ok = False
                    self._increment_error()

            # waiting to min time
            if action.action_type == ActionType.PICKUP and time < action_data.action.min_time:
                pause_duration = action_data.action.min_time - time
                time = action_data.action.min_time
                if (pause_duration > timedelta(seconds=min_pause_length)):
                    driving_start = time

            if (max_pause_interval and time - driving_start > timedelta(seconds=max_pause_interval)):
                print(
                    "in Request {} driver is active {} min, max is {}.".format(
                        action_data.action.request.index,
                        time - driving_start,
                        max_pause_interval
                        )
                )
                plan_ok = False
                self._increment_error()

            max_ride_time = instance.darp_instance_config.max_ride_time

            #  max ride time check - dropoff
            if max_ride_time and is_drop_off:
                ride_time = time - departure_times[request.index]
                if ride_time > max_ride_time:
                    print(
                        "[{}. plan] Max ride time exceeded for request {}: ride time was {} while max ride time is {}".format(
                            plan_counter,
                            request.index,
                            ride_time,
                            max_ride_time
                        )
                    )
                    plan_ok = False
                    self._increment_error()

            # service time
            time += timedelta(seconds=int(action_data.action.service_time))
            max_departure_time = action_data.departure_time + timedelta(
                seconds=instance.darp_instance_config.max_pickup_delay
            )

            # departure time check
            if max_departure_time < time:
                print(
                    "[{}. plan, {}. action] Departure time mismatch (was {}, must be higher than {}) when handling request {}".format(
                        plan_counter, action_index + 1, action_data.departure_time, time, action_data.action.request.index
                                  )
                )
                self._increment_error()

            time = action_data.departure_time

            #  max ride time check - pickup
            if is_pickup:
                departure_times[request.index] = time

            previous_action = action_data.action

        # return to init position
        if previous_action and instance.darp_instance_config.return_to_depot:
            travel_time_to_depot = travel_time_provider.get_travel_time(previous_action.node, plan.vehicle.initial_position)
            travel_time_to_depot = travel_time_to_depot / travel_time_divider
            cost += travel_time_to_depot
            time += timedelta(seconds=int(travel_time_to_depot))

        # max route time check
        max_route_duration = instance.darp_instance_config.max_route_duration
        if max_route_duration and time - plan.departure_time > max_route_duration:
            print(
                "[{}. plan] Total max route duration exceeded: Duration is {} but maximum allowed route duration is {}".format(
                    plan_counter,
                    time - plan.departure_time,
                    max_route_duration
                    )
            )
            plan_ok = False
            self._increment_error()

        # cost check
        if plan.cost is not None and abs(cost - plan.cost) > 1:
            logging.warning(
                "{} plan cost mismatch. expected: {}, computed: {}".format(plan_counter, plan.cost, cost)
            )
            plan_ok = False
            self._increment_error()

        if plan_ok:
            logging.debug("[{}. plan] with {} actions OK".format(plan_counter, len(plan.actions)))
        else:
            logging.warning("[{}. plan] with {} actions NOT OK".format(plan_counter, len(plan.actions)))

        return cost, plan_ok, served_requests

    def check_solution(self, instance: DARPInstance, solution: Solution) -> Tuple[bool, Dict[Failure, int]]:
        failures = {Failure.PLAN_DEPARTURE_TIME: 0}

        if not solution.feasible:
            logging.info("Solution is infeasible")
            return True, failures

        used_vehicles = set()
        solution_ok = True
        served_requests = set()
        total_cost = 0.0

        plan_counter = 1

        for plan in solution.vehicle_plans:
            cost, plan_ok, plan_served_requests = self.check_plan(plan, plan_counter, instance, used_vehicles, failures)
            total_cost += cost
            if not plan_ok:
                solution_ok = False

            served_requests.update(plan_served_requests)
            plan_counter += 1

        # all request served check
        for request in instance.requests:
            if request not in served_requests and request.index not in solution.dropped_requests:
                print("Request {} not served while not being in dropped requests list.".format(request.index))
                solution_ok = False
                self._increment_error()

        # total cost check
        if solution.cost is not None:
            if abs(total_cost - solution.cost) > 1:
                print(
                    "Solution cost not computed correctly. Solution cost: {}, total cost of all plans: {}".format(
                        solution.cost, total_cost
                    )
                )
                solution_ok = False
                self._increment_error()

        if solution_ok:
            logging.info("Solution OK")
        else:
            logging.warning("Solution NOT OK")

        return solution_ok, failures

    def check_all_solutions(self, root_paths: List[Path], log_all=True) -> pd.DataFrame:
        logging.info('Checking solutions in the following root paths: \n%s', '\n'.join((str(path) for path in root_paths)))

        dirs = []

        for root_path in root_paths:
            for root, dir, files in os.walk(root_path):
                for file in files:
                    filename = os.fsdecode(file)
                    if filename == "config.yaml-solution.json":
                        filepath = os.path.join(root, filename)
                        dirs.append((root, filepath))
                        break

        dir_df = pd.DataFrame(dirs, columns=["root", "solution path"])
        logging.info("%d solutions found", len(dir_df))

        # sort by area
        dir_df['area'] = dir_df['root'].apply(lambda path: Path(path).parts[-5])
        dir_df.sort_values(by=['area'], inplace=True)

        stats = []
        last_instance_path = None
        last_instance = None
        travel_time_provider = None
        last_area = None
        columns = ['solution path', 'ok']
        for root, solution_path, area in zip(dir_df['root'], dir_df['solution path'], dir_df['area']):
            config_path = os.path.join(root, "config.yaml")
            experiment_config = darpinstances.experiments.load_experiment_config(config_path)
            instance_path = Path(experiment_config['instance'])
            if instance_path == last_instance_path:
                instance = last_instance
            else:
                if last_area == area:
                    instance, _ = darpinstances.solution_checker.load_instance(
                        instance_path,
                        last_instance.travel_time_provider
                    )
                else:
                    instance, _ = darpinstances.solution_checker.load_instance(instance_path)

            solution = darpinstances.solution.load_solution(solution_path, instance)

            ok, failures = self.check_solution(instance, solution)
            sol_record = [solution_path, ok]
            sol_record.extend([count for _, count in failures.items()])
            stats.append(sol_record)
            if len(columns) == 2:
                columns.extend(failures.keys())

            last_instance_path = instance_path
            last_instance = instance
            last_area = area

        stat_df = pd.DataFrame(stats)
        stat_df.columns = columns

        logging.info("Checked %d solutions", len(stats))
        if log_all:
            pd.set_option('display.max_colwidth', None)
            pd.set_option('display.max_rows', None)
            logging.info("Stats: \n%s", stat_df)

            stats_er = stat_df[stat_df['ok'] == False]
            if len(stats_er) > 0:
                logging.error("Found %d errors", len(stats_er))
                logging.error("Error solutions: \n%s", stats_er)

        return stat_df


def load_data(solution_file_path: Path, instance_path: Optional[Path], demand_file_name: Optional[str] = None) -> Tuple[DARPInstance, Solution]:
    check_file_exists(solution_file_path)
    solution_dir_path = solution_file_path.parent
    os.chdir(solution_dir_path)

    if instance_path is None:
        experiment_config_path = solution_dir_path / "config.yaml"
        experiment_config = darpinstances.experiments.load_experiment_config(experiment_config_path)
        instance_path = Path(experiment_config['instance'])

    instance, _ = load_instance(instance_path, demand_file_name=demand_file_name)

    solution = darpinstances.solution.load_solution(solution_file_path, instance)

    return instance, solution

    # uncoment the following line to read the Cordeau & Laport solution files  # solution = darpbenchmark.cordeau_benchmark.load_cordeau_solution(cordeau_solution_path, vehicle_map, request_map)


def load_instance(
    instance_path: Path,
    travel_time_provider: Optional[TravelTimeProvider] = None,
    demand_file_name: Optional[str] = None
) -> Tuple[DARPInstance, TravelTimeProvider]:
    if instance_path.suffix == '.yaml':
        instance = darpinstances.instance.load_instance(instance_path, travel_time_provider, demand_file_name)
        travel_time_provider = instance.travel_time_provider
    else:
        instance = load_cordeau(instance_path)
        travel_time_provider = darpinstances.instance.EuclideanTravelTimeProvider(60)
    return instance, travel_time_provider


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scrip for checking DARP solutions')
    parser.add_argument('solution', type=Path, help='Path to solution file (JSON)')
    parser.add_argument('-i', '--instance', type=str, help='Path to instance config file (YAML)', required=False)

    args = parser.parse_args()

    solution_file_path = args.solution
    logging.info("Checking solution: %s", solution_file_path)
    check_file_exists(solution_file_path)

    if args.instance:
        instance_path = Path(args.instance)
        logging.info("Instance path provided as argument: %s", instance_path)
    else:
        # if instance path is not provided, try to load it from the experiment config
        exp_config_path = solution_file_path.parent / "config.yaml"
        logging.info("Instance path not provided, trying to load it from the experiment config: %s", exp_config_path)
        check_file_exists(exp_config_path)
        experiment_config = darpinstances.experiments.load_experiment_config(exp_config_path)
        instance_path = Path(experiment_config['instance'])
        logging.info("Instance path loaded from the experiment config: %s", instance_path)
        os.chdir(solution_file_path.parent)

    check_file_exists(instance_path)

    instance, solution = load_data(solution_file_path, instance_path)
    check_solution(instance, solution)
