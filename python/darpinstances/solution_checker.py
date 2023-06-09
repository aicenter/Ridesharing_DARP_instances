import os.path
from pathlib import Path
from typing import Tuple, Set, Optional

import darpinstances.experiments
import darpinstances.inout
import darpinstances.instance
from darpinstances.cordeau_benchmark import load as load_cordeau
from darpinstances.inout import check_file_exists
from darpinstances.instance import DARPInstance, TravelTimeProvider
from darpinstances.instance_generation.instance_objects import Request, Action, ActionType
from darpinstances.solution import VehiclePlan, Solution

darp_folder_path = Path("C:\Google Drive/AIC Experiment Data\DARP")
# darp_folder_path = r"D:\Google Drive/AIC Experiment Data\DARP"

# solution_file_path = r"C:\AIC Experiment Data\DARP\Results\Real Demand\NYC memory benchmark/config.yaml-solution.json"
# solution_file_path = r"C:\AIC Experiment Data\DARP\Results\Real Demand\Manhattan/vga_chaining-batch_30_s/config.yaml-solution.json"
# solution_file_path = r"C:\AIC Experiment Data\DARP\Results\Manhattan/max_delay-exp_length_SA-min_vehicles/exp_length_900_s-max_delay_5/vga_chaining-batch_length_30_s/instance-trips-max_delay_300-time_to_start_120-vehicle_capacity_4.di-solution.json"
# solution_file_path = r"C:\Google Drive/AIC Experiment Data\DARP\Results\final-real_speeds\DC-more_vehicles\30_min\ih/config.yaml-solution.json"
# solution_file_path = r"C:\Google Drive/AIC Experiment Data\DARP\Results\final-real_speeds\DC-more_vehicles\30_min\halns-ih/config.yaml-solution.json"
# solution_file_path = r"C:\Google Drive\AIC Experiment Data\DARP\Results\final_halns_test/config.yaml-solution.json"
# solution_file_path = r"D:\Google Drive/AIC Experiment Data\DARP\Results\final-real_speeds\DC-more_vehicles\15_min/halns-ih/config.yaml-solution.json"
# solution_file_path = r"C:\Google Drive/AIC Experiment Data\DARP\Results\final-real_speeds\NYC-more_vehicles\05_min/ih/config.yaml-solution.json"
# solution_file_path = darp_folder_path + r"\Results\final-real_speeds\NYC\05_min/ih/config.yaml-solution.json"
# solution_file_path = darp_folder_path + r"\Results\ihtest/config.yaml-solution.json"
# solution_file_path = darp_folder_path / r"ITSC_instance_paper\old\incorrect results\DC\start_18-00\duration_015_min\max_delay_03_min\halns/config.yaml-solution.json"
solution_file_path = darp_folder_path / r"C:\\Google Drive/AIC Experiment Data\\DARP/Results/test/config.yaml-solution.json"
instance_path = darp_folder_path / r"ITSC_instance_paper\old\Instances\DC\instances/start_18-00\duration_015_min\max_delay_03_min\config.yaml"


def load_data(solution_file_path: Path, instance_path: Optional[Path]) -> Tuple[DARPInstance, Solution]:
    check_file_exists(str(solution_file_path))
    solution_dir_path = solution_file_path.parent
    os.chdir(solution_dir_path)

    if instance_path is None:
        config_path = os.path.join(solution_dir_path, "config.yaml")
        experiment_config = darpinstances.experiments.load_experiment_config(config_path)
        instance_path = Path(experiment_config['instance'])

    instance, _ = load_instance(str(instance_path))

    # request_map = dict()
    # for request in instance.requests:
    #     request_map[request.index] = request
    #
    # vehicle_map = dict()
    # for vehicle in instance.vehicles:
    #     vehicle_map[vehicle.index] = vehicle

    solution = darpinstances.solution.load_solution(str(solution_file_path), instance)

    return instance, solution

    # uncoment the following line to read the Cordeau & Laport solution files
    # solution = darpbenchmark.cordeau_benchmark.load_cordeau_solution(cordeau_solution_path, vehicle_map, request_map)


def load_instance(instance_path: str) -> Tuple[DARPInstance, TravelTimeProvider]:
    if instance_path.endswith('yaml'):
        instance = darpinstances.instance.read_instance(instance_path)
        travel_time_provider = instance.travel_time_provider
    else:
        instance = load_cordeau(instance_path)
        travel_time_provider = darpinstances.instance.EuclideanTravelTimeProvider(60)
    return instance, travel_time_provider


def check_plan(plan: VehiclePlan, plan_counter: int, instance: DARPInstance, used_vehicles: set) \
        -> Tuple[int, bool, Set[Request]]:
    plan_ok = True
    cost = 0

    if plan.departure_time < instance.darp_instance_config.start_time:
        plan_ok = False
        print("[{}. plan]: departure time {} is smaller then the instance start time ({})"
              .format(plan_counter, plan.departure_time, instance.darp_instance_config.start_time))

    time = plan.departure_time
    free_capacity = plan.vehicle.capacity
    previous_action: Action = None
    onboard_requests = set()
    # departure_times = np.zeros(len(instance.requests))
    departure_times = dict()
    vehicle_index = plan.vehicle.index
    travel_time_provider = instance.travel_time_provider
    served_requests = set()

    if not instance.darp_instance_config.virtual_vehicles:
        if vehicle_index in used_vehicles:
            print("[{}. plan]: Vehicle {} already used".format(plan_counter, vehicle_index))
            plan_ok = False
        used_vehicles.add(vehicle_index)

    for action_index, action_data in enumerate(plan.actions):
        request = action_data.action.request

        # onboard check
        if action_data.action.action_type == ActionType.PICKUP:
            onboard_requests.add(request)
        else:
            if request in onboard_requests:
                onboard_requests.remove(request)
                served_requests.add(request)
            else:
                print("[{}. plan] Request {} dropped off while not being picked up first.".format(plan_counter,
                                                                                                  request.index))
                plan_ok = False
        # break

        if previous_action:
            travel_time = travel_time_provider.get_travel_time(previous_action.node, action_data.action.node)
        else:
            if instance.darp_instance_config.virtual_vehicles:
                travel_time = plan.vehicle.time_to_start
            else:
                travel_time = travel_time_provider.get_travel_time(plan.vehicle.initial_position,
                                                                   action_data.action.node)

        time += travel_time

        # arrival time check
        if action_data.arrival_time != time:
            print("[{}. plan, {}. Action] Arrival time mismatch (expected {}, was {}) when handling request {}".format(
                plan_counter, action_index + 1, time, action_data.arrival_time, action_data.action.request.index))

        # max time check
        if time > action_data.action.max_time:
            print("[{}. plan, {}. Action] Action max time exceeded ({} > {}) when handling request {}.".format(
                plan_counter, action_index, time, action_data.action.max_time, action_data.action.request.index))
            plan_ok = False
        # break

        # capacity check
        if action_data.action.action_type == ActionType.PICKUP:
            if free_capacity == 0:
                print(
                    "[{}. plan] Pickup action performed when vehicle was already full when handling request {}".format(
                        plan_counter, action_data.action.request.index))
                plan_ok = False
            # break
            free_capacity -= 1
        else:
            free_capacity += 1

        cost += travel_time

        # waiting to min time
        if time < action_data.action.min_time:
            time = action_data.action.min_time

        max_ride_time = instance.darp_instance_config.max_ride_time

        #  max ride time check - dropoff
        if max_ride_time and action_data.action.action_type == ActionType.DROP_OFF:
            ride_time = time - departure_times[request.index]
            if ride_time > max_ride_time:
                print("[{}. plan] Max ride time exceeded for request {}: ride time was {} while max ride time is {}"
                      .format(plan_counter, request.index, ride_time, max_ride_time))
                plan_ok = False

        # service time
        time += action_data.action.service_time

        # departure time check
        if action_data.departure_time < time:
            print(
                "[{}. plan, {}. action] Departure time mismatch (was {}, must be higher than {}) when handling request {}"
                .format(plan_counter, action_index + 1, action_data.departure_time, time,
                        action_data.action.request.index))

        time = action_data.departure_time

        #  max ride time check - pickup
        if action_data.action.action_type == ActionType.PICKUP:
            departure_times[request.index] = time

        previous_action = action_data.action

    # return to init position
    if previous_action and instance.darp_instance_config.return_to_depot:
        travel_time_to_depot = travel_time_provider.get_travel_time(previous_action.node, plan.vehicle.initial_position)
        cost += travel_time_to_depot
        time += travel_time_to_depot

    # max route time check
    max_route_duration = instance.darp_instance_config.max_route_duration
    if max_route_duration and time - plan.departure_time > max_route_duration:
        print("[{}. plan] Total max route duration exceeded: Duration is {} but maximum allowed route duration is {}"
              .format(plan_counter, time - plan.departure_time, max_route_duration))
        plan_ok = False

    # cost check
    if cost != plan.cost:
        print(
            "[{}. plan] Total cost does not match: cost in solution is {} but computed cost is {}".format(plan_counter,
                                                                                                          plan.cost,
                                                                                                          cost))
        plan_ok = False

    if plan_ok:
        print("[{}. plan] with {} actions OK".format(plan_counter, len(plan.actions)))
    else:
        print("[{}. plan] with {} actions NOT OK".format(plan_counter, len(plan.actions)))

    return cost, plan_ok, served_requests


def check_solution(instance: DARPInstance, solution: Solution) -> bool:
    used_vehicles = set()
    solution_ok = True
    served_requests = set()
    total_cost = 0

    plan_counter = 1
    for plan in solution.vehicle_plans:
        cost, plan_ok, plan_served_requests = check_plan(plan, plan_counter, instance, used_vehicles)
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
        # break

    # total cost check
    if total_cost != solution.cost:
        print(
            "Solution cost not computed correctly. Solution cost: {}, total cost of all plans: {}".format(solution.cost,
                                                                                                          total_cost))
        solution_ok = False

    if solution_ok:
        print("Solution OK")
    else:
        print("Solution NOT OK")

    return solution_ok


if __name__ == '__main__':
    instance, solution = load_data(solution_file_path, instance_path)
    check_solution(instance, solution)
