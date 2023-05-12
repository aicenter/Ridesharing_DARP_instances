import copy
import datetime
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Union

import darpinstances.experiments
import darpinstances.inout
import darpinstances.instance
import pandas as pd

ser_pattern = re.compile(r".+-\d+$")
batch_pattern = re.compile(r".+b(\d+).*$")


def load_connection_stats(filepath: str) -> int:
    used_connections = 0
    with open(filepath, 'r') as file:
        for line in file:
            if "From" in line:
                break
            if line.rstrip().endswith("1"):
                used_connections += 1
    return used_connections


def load_results_from_folder(folder_path: str, skip_used_connections: bool = False) \
        -> Tuple[Union[dict, List[dict]], Union[dict, List[dict]]]:
    """
    Loads solution and performance files from folder as JSON objects.
    Also, the chaining connections stats are loaded here.
    :param folder_path: input path
    :return: Two lists, the first one containing solutions, and the second one containing performances
    """
    solutions = []
    performances = []
    directory = os.fsencode(folder_path)
    used_connections = -1
    for file in os.listdir(directory):
        filename = os.fsdecode(file)
        filepath = os.path.join(folder_path, filename)
        if "solution.json" in filename:
            solutions.append(darpinstances.inout.load_json(filepath))
        elif "performance.json" in filename:
            performances.append(darpinstances.inout.load_json(filepath))
        elif not skip_used_connections and filename == "chaining_solution.sol":
            used_connections = load_connection_stats(filepath)

    if len(solutions) > 0:
        solutions[-1]['used_connections'] = used_connections
    else:
        logging.warning("No solution found in folder: %s", folder_path)

    assert len(solutions) == len(performances)

    if len(solutions) == 1:
        return solutions[0], performances[0]

    return solutions, performances


def load_instance_results(instance_path: str) -> Tuple[Dict[str, List[dict]], Dict[str, List[dict]]]:
    """
    Loads all solutions and performance result from an instance folder. It should aggregate solutions and performances
    according to the solution method.
    :param instance_path: path to the instance folder
    :return: two dictionaries, the first one for solutions, and the second one for performances. Each one
    contains solutions/performances as lists maped by a solution method name.
    """
    solutions = {}
    performances = {}
    for file in os.listdir(instance_path):
        filename = os.fsdecode(file)
        filepath = os.path.join(instance_path, filename)
        if os.path.isdir(filepath) is not None:
            if ser_pattern.match(filename):
                method = filename.rsplit('-', 1)[0]
            else:
                method = filename
            if method not in solutions:
                solutions[method] = []
                performances[method] = []
            solutions_from_dir, performance_from_dir = load_results_from_folder(filepath)
            if isinstance(solutions_from_dir, list):
                solutions[method].extend(solutions_from_dir)
                performances[method].extend(performance_from_dir)
            else:
                solutions[method].append(solutions_from_dir)
                performances[method].append(performance_from_dir)

    return solutions, performances


def load_instance_series(series_file_path: str) -> Tuple[
    Dict[str, Dict[str, List[dict]]], Dict[str, Dict[str, List[dict]]]]:
    solutions = {}
    performances = {}

    for file in os.listdir(series_file_path):
        filename = os.fsdecode(file)
        filepath = os.path.join(series_file_path, filename)
        if os.path.isdir(filepath):
            solutions_from_dir, performance_from_dir = load_instance_results(filepath)
            # instance_name = filename.split('-')[0]
            instance_name = filename
            solutions[instance_name] = solutions_from_dir
            performances[instance_name] = performance_from_dir

    return solutions, performances


def get_processed_results(
        solution: dict,
        performance: dict,
        return_as_dict: bool = False
        # instance: DARPInstance
) -> Tuple[Union[list, dict], List[int]]:
    """
    This method processes the solution and performance JSON data and provides statistic as list
    :param solution: solution JSON object
    :param performance: performance JSON object
    :return:
    """
    plan_count = 0
    req_count = 0
    avg_occupancy_sum = 0
    total_driving_duration = 0
    total_waiting_duration = 0
    tts_cost = 0
    total_delay = 0
    ocuppancies = [0, 0, 0, 0, 0]

    for plan in solution["plans"]:
        if len(plan["actions"]) > 0:
            pickup_times = dict()

            plan_count += 1

            # occupancy related
            current_occupancy = 0
            prev_departure = plan['departure_time']

            tts_cost += plan["actions"][0]['arrival_time'] - plan['departure_time']

            for action in plan["actions"]:
                driving_duration = action['arrival_time'] - prev_departure
                assert driving_duration >= 0

                waiting_duration = action['departure_time'] - action['arrival_time']
                total_driving_duration += driving_duration
                total_waiting_duration += waiting_duration
                avg_occupancy_sum += driving_duration * current_occupancy
                ocuppancies[current_occupancy] += driving_duration
                if action['action']['type'] == 'pickup':
                    current_occupancy += 1
                    req_count += 1
                    pickup_times[action['action']['request_index']] = action['departure_time']
                else:
                    trip_duration = action['arrival_time'] - pickup_times[action['action']['request_index']]
                    # min_time = instance.request_map[action['action']['request_id']].min_time
                    min_time = 0
                    delay = trip_duration - min_time
                    total_delay += delay
                    current_occupancy -= 1
                prev_departure = action['departure_time']

    avg_occupancy = avg_occupancy_sum / total_driving_duration
    tts_cost_per_plan = tts_cost / plan_count

    data = {
        'cost_minutes': solution['cost_minutes'],
        'total_time': performance['total_time'] / 1000,
        'dropped_requests': len(solution['dropped_requests']),
        'avg_delay': total_delay / req_count,
        'plan_count': plan_count,
        'req_count': req_count,
        'avg_occupancy': avg_occupancy,
        'used_connections': solution['used_connections'],
        'total_driving_duration': total_driving_duration,
        'total_waiting_duration': total_waiting_duration,
        'avg_waiting_duration': total_waiting_duration / plan_count,
        'tts_cost': tts_cost,
        'tts_cost_per_plan': tts_cost_per_plan
    }

    if return_as_dict:
        return data, ocuppancies
    else:
        return list(data.values()), ocuppancies


def instance_results_to_dataframe(
        solutions: Dict[str, List[dict]],
        performances: Dict[str, List[dict]],
        # instance: DARPInstance
) -> pd.DataFrame:
    """
    Converts solution and performance data for instance into a dataframe, where each row corresponds to a method, and
    each column to some statistic.
    :param solutions: solution data
    :param performances: performance data
    :return: results dataframe
    """
    instance_data = []
    for (method, solutions_for_method), performances_for_method in zip(solutions.items(), performances.values()):
        for solution, performance in zip(solutions_for_method, performances_for_method):
            experiment_data, _ = get_processed_results(solution, performance)
            experiment_data.insert(0, rename_method(method))
            instance_data.append(experiment_data)

    columns = [
        'method',
        'cost_minutes',
        'comp_time_s',
        'dropped_requests',
        'delay',
        'plan_count',
        'request_count',
        'occupancy',
        'used_connections',
        'total_driving_duration',
        'total_waiting_duration',
        'wait_time_per_plan',
        'travel_time_to_start',
        'travel_time_to_start_per_plan'
    ]
    out = pd.DataFrame(instance_data, columns=columns)
    out.sort_values(by=['method'], inplace=True, key=lambda col: pd.Series((get_method_value(value) for value in col)))
    return out


def rename_method(method_name: str) -> str:
    method_name = method_name.replace('ih', 'IH')
    method_name = method_name.replace('vga', 'VGA')
    method_name = method_name.replace('halns', 'HALNS')
    method_name = method_name.replace('_chaining', '-ch')
    method_name = method_name.replace('-batch_', ' b')
    method_name = method_name.replace('_s', '')
    method_name = method_name.replace('-limited', ' lim')
    return method_name


def get_method_value(method_name: str) -> int:
    hardcoded_order = {'IH': 0, 'HALNS': 1, 'HALNS-IH': 2, 'HALNS-VGA': 10000, 'VGA': 10001}
    val = hardcoded_order[method_name] if method_name in hardcoded_order else _compute_vga_chaining_value(method_name)
    return val


def _compute_vga_chaining_value(method_name: str) -> int:
    batch_search = re.search(batch_pattern, method_name)
    batch_length = int(batch_search.group(1))
    limited = method_name.endswith('lim')
    value = batch_length
    if limited:
        value -= 1
    return value


def instance_series_results_to_dataframe(
        solutions: Dict[str, Dict[str, List[dict]]],
        performances: Dict[str, Dict[str, List[dict]]]
) -> pd.DataFrame:
    all_data: Optional[pd.DataFrame] = None
    for (instance, solutions_per_instance), performances_per_instance in zip(solutions.items(), performances.values()):
        df_per_instance = instance_results_to_dataframe(solutions_per_instance, performances_per_instance)
        df_per_instance['instance'] = instance
        if all_data is None:
            all_data = df_per_instance
        else:
            all_data = pd.concat([all_data, df_per_instance])

    return all_data


def compute_plan_statistics(solution: dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
    plan_stats = []
    for plan in solution["plans"]:
        if len(plan["actions"]) > 0:
            action_count = len(plan["actions"])
            waiting_time = 0
            tts_cost = 0
            avg_occupancy = 0
            cost_per_request = 0

            # occupancy related
            current_occupancy = 0
            prev_departure = plan['departure_time']
            avg_occupancy_sum = 0

            tts_cost = plan["actions"][0]['arrival_time'] - plan['departure_time']

            for action in plan["actions"]:
                waiting_time += action['departure_time'] - action['arrival_time']
                driving_duration = action['arrival_time'] - prev_departure
                waiting_duration = action['departure_time'] - action['arrival_time']
                avg_occupancy_sum += driving_duration * current_occupancy
                if action['action']['type'] == 'pickup':
                    current_occupancy += 1
                else:
                    current_occupancy -= 1
                prev_departure = action['departure_time']

            if plan['cost'] > 0:
                avg_occupancy = avg_occupancy_sum / plan['cost']
                cost_per_request = plan['cost'] / (action_count / 2)

            duration = plan['arrival_time'] - plan['departure_time']

            plan_stats.append(
                [
                    plan['vehicle']['index'],
                    plan['cost'],
                    cost_per_request,
                    action_count,
                    waiting_time,
                    tts_cost,
                    avg_occupancy,
                    duration
                ]
            )

    columns = [
        'vehicle',
        'cost',
        'cost_per_request',
        'action_count',
        'waiting_time',
        'time_to_start',
        'average_occupancy',
        'duration'
    ]
    dropped_requests = []
    for dropped_request in solution["dropped_requests"]:
        dropped_requests.append([
            dropped_request['index'],
            datetime.datetime.fromtimestamp(dropped_request['pickup']['min_time'])
        ])

    return pd.DataFrame(plan_stats, columns=columns), pd.DataFrame(dropped_requests, columns=["index", 'time'])


def get_delays_from_solution(solution: dict, instance: pd.DataFrame) -> List[int]:
    delays = []
    for plan in solution["plans"]:
        if len(plan["actions"]) > 0:
            pickup_times = dict()

            # occupancy related
            current_occupancy = 0
            prev_departure = plan['departure_time']

            for action in plan["actions"]:
                driving_duration = action['arrival_time'] - prev_departure
                assert driving_duration >= 0

                if action['action']['type'] == 'pickup':
                    pickup_times[action['action']['request_index']] = action['departure_time']
                else:
                    trip_duration = action['arrival_time'] - pickup_times[action['action']['request_index']]
                    # min_time = instance.request_map[action['action']['request_id']].min_time
                    min_time = instance.iloc[action['action']['request_index']]['min_travel_time']
                    delay = trip_duration - min_time
                    assert delay >= 0
                    delays.append(delay)
                prev_departure = action['departure_time']

    return delays


def load_all_data_for_result(path: Path) -> Optional[Tuple[Dict,List]]:
    result, performance = load_results_from_folder(str(path))
    if type(result) is list:
        if len(result) == 0:
            return None
    data, occupancies = get_processed_results(result, performance, return_as_dict=True)

    config_path = path / 'config.yaml'
    exp_config = darpinstances.experiments.load_experiment_config(str(config_path))
    data['method'] = exp_config['method']

    instance_config_path = path / exp_config['instance']
    instance_config = darpinstances.instance.load_instance_config(str(instance_config_path))
    data['max_delay'] = int(instance_config['max_prolongation'])
    data['start_time'] = datetime.strptime(instance_config['demand']['min_time'], '%Y-%m-%d %H:%M:%S')
    data['end_time'] = datetime.strptime(instance_config['demand']['max_time'], '%Y-%m-%d %H:%M:%S')
    data['duration_minutes']  = int((data['end_time'] - data['start_time']).total_seconds() / 60)

    return data, occupancies


def load_aggregate_stats_in_dir(path: Path) -> pd.DataFrame:
    logging.info(f"Loading aggregate stats in {path}")
    data = []

    for root, dir, files in os.walk(path):
        for file in files:
            filename = os.fsdecode(file)
            if filename == "config.yaml":
                exp_config_filepath = Path(root) / filename
                d = load_all_data_for_result(exp_config_filepath.parent)
                if d is not None:
                    data.append(d[0])

    df = pd.DataFrame(data)
    return df


def load_occupancies_in_dir(path: Path) -> Optional[pd.DataFrame]:
    logging.info(f"Loading occupancy stats in {path}")
    out_data = []

    for root, dir, files in os.walk(path):
        for file in files:
            filename = os.fsdecode(file)
            if filename == "config.yaml":
                exp_config_filepath = Path(root) / filename
                d = load_all_data_for_result(exp_config_filepath.parent)
                if d is not None:
                    agg_data_for_result, occupancies = d[0], d[1]
                    for i, o in enumerate(occupancies):
                        oc = copy.deepcopy(agg_data_for_result)
                        oc['occupancy'] = i
                        oc['vehicle_hours'] = o / 3600
                        out_data.append(oc)

    if len(out_data) == 0:
        return None

    return pd.DataFrame(out_data)
