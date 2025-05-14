import os
from pathlib import Path
import pandas as pd
from itertools import product
import shutil
from datetime import datetime, timedelta

from darpinstances.instance import load_instance_config
from darpinstances.instance_generation.generate_config import generate_config
from darpbenchmark.sizing import calculate_sizing_for_instance
from darpinstances.instance_generation.map import NearestNodeProvider, get_map
from darpinstances.instance_generation.demand_generation import generate_demand, generate_uniform_trip_times
from darpinstances.instance_generation.vehicles import generate_vehicles


PATH = Path.cwd()
INSTANCE_PATH_OLD = PATH.parents[0] / "Instances"
INSTANCE_PATH_RCI = PATH.parents[0] / "rci" / "Instances"
RESULTS_PATH_SIZING = PATH.parents[0] / "sizing" / "Results"
RESULTS_PATH_RCI = PATH.parents[0] / "rci" / "Results"

RCI = True
SIZING = False

FILE_TO_SAMPLE = 'requests.csv'
DIR_TO_COPY = 'shapefiles'

def create_custom_results_config(instance_path, method, outdir):
    config = {}
    config['instance'] = instance_path
    config['method'] = method
    config['outdir'] = outdir
    return config

def setup_config_rci(vehicle_count, city, starts_str, start_str, i, j, capacity, delay, sample_size, methods, duration):
    # setup new instance config
    new_dir, new_config_path, relative_path = setup_instance_paths(city, starts_str, start_str, i, delays_str, j, capacity, sample_size, rci=True)

    # load old config
    old_dir, old_config_path = locate_old_config(city, starts_str, start_str, i)

    old_config = load_instance_config(old_config_path)
    new_config = modify_configs(old_config, capacity, delay, sample_size)
    if vehicle_count:
        new_config['vehicles']['vehicle_count'] = vehicle_count

    # generate new config
    generate_config(new_config, new_config_path)

    start_time_str = new_config['demand']['min_time']
    vehicle_size = sample_requests_and_copy_files(old_dir, new_dir, sample_size, start_time_str, duration)

    generate_vehicle_shapefiles(vehicle_size, new_config, old_dir, new_dir)

    # setup new results configs
    setup_results_configs(methods, city, relative_path)

def setup_results_configs(methods, city, relative_path):
    for method in methods:

        results_dir = RESULTS_PATH_RCI / city / relative_path / method
        os.makedirs(results_dir, exist_ok=True)
        results_path = results_dir / "config.yaml"

        if RCI:
            new_config_path =  f'Instances/{city}/instances' / relative_path / 'config.yaml'
            results_dir = Path(f'Results/{city}') / relative_path / method
        
        results_config = create_custom_results_config(str(new_config_path), method, str(results_dir))

        generate_config(results_config, results_path)

def generate_vehicle_shapefiles(desired_vehicle_count, instance_config, instance_dir_old, instance_dir_new):
    instance_config['area_dir'] = "../../../../"
    os.chdir(instance_dir_old)
    map_nodes, _ = get_map(instance_config)
    crs_metric = instance_config['map']['SRID_plane']
    nodes = map_nodes.to_crs(f'epsg:{crs_metric}')
    nearest_node_provider = NearestNodeProvider(nodes)

    os.chdir(instance_dir_new)
    instance_config['vehicles']['positions'] = 'random'
    generate_vehicles(map_nodes, instance_config, nearest_node_provider, desired_vehicle_count)
    os.chdir(PATH)

def modify_configs(instance_config, capacity, delay, size=1):
    instance_config['vehicles']['vehicle_capacity'] = capacity
    instance_config['demand']['filepath'] = 'requests.csv'
    instance_config['demand']['sample'] = size
    instance_config['max_prolongation'] = delay*60
    instance_config['area_dir'] = "../../../../../../" # capacity/sample
    # instance_config['area_dir'] = "../../../../../" # capacity
    instance_config['vehicles'].pop('vehicle_count', None)
    instance_config['map'].pop('path', None)
    instance_config.pop('instance_dir', None)
    return instance_config

def sample_requests(req_df, sample_size, destination_file, start_time_str, duration_mins) -> int:
    if len(req_df.columns) == 4:
        # remove the last column - not necessary for sampling
        req_df = req_df.iloc[:, :-1]

    base_count = len(req_df)
    sample_count = int(base_count * sample_size)

    if sample_size > 1:
        extra_count = sample_count - base_count
        extra_df = req_df.sample(n=extra_count, random_state=1)
        new_times = generate_new_time_for_sampled_requests(start_time_str, duration_mins, extra_count)
        extra_df['time_ms'] = new_times
        sampled_df = pd.concat([req_df, extra_df], ignore_index=True)
    else:
        sampled_df = req_df.sample(n=sample_count, random_state=1)
    sampled_df.reset_index(drop=True, inplace=True)
    sampled_df.to_csv(destination_file, index=False, sep='\t')
    return len(sampled_df)

def generate_new_time_for_sampled_requests(start_time_str, duration_mins, n):
    start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
    end_time = start_time + timedelta(minutes=duration_mins)

    min_time = int(start_time.time().hour * 3600 + start_time.time().minute * 60 + start_time.time().second)
    max_time = int(end_time.time().hour * 3600 + end_time.time().minute * 60 + end_time.time().second)

    new_times = generate_uniform_trip_times(min_time, max_time, n).astype(int)
    return new_times

def setup_instance_paths(city, starts_str, start_str, i, delays_str, j, capacity, sample_size=1, rci=False):
    relative_path = Path(f'start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[j]}/capacity_{capacity}')
    if sample_size != 1:
        relative_path = relative_path / f'sample_{sample_size}'
    instance_path_relative = Path(f'{city}/instances/') / relative_path
    if rci:
        instance_dir_new = INSTANCE_PATH_RCI / instance_path_relative
        instance_path = instance_dir_new / "config.yaml"
        os.makedirs(instance_dir_new, exist_ok=True)
        return instance_dir_new, instance_path, relative_path
    else:
        instance_dir_new = INSTANCE_PATH_OLD / instance_path_relative
        instance_path = instance_dir_new / "config.yaml"
        os.makedirs(instance_dir_new, exist_ok=True)
        return instance_dir_new, instance_path

def locate_old_config(city, starts_str, start_str, i):
    instance_dir_old = INSTANCE_PATH_OLD / f'{city}/instances/start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[0]}'
    instance_config_path = instance_dir_old / 'config.yaml'

    if not instance_config_path.exists() and starts_str[start_str][i] == '2_h':
        instance_dir_old = INSTANCE_PATH_OLD / f'{city}/instances/start_{start_str}/duration_02_h/max_delay_{delays_str[0]}'
        instance_config_path = instance_dir_old / 'config.yaml'

    return instance_dir_old, instance_config_path

def sample_requests_and_copy_files(instance_dir_old, instance_dir_new, sample_size, start_time_str, duration_mins):
    # INSTEAD of copying the requests and vehicles, we will sample from them
    src = instance_dir_old / FILE_TO_SAMPLE
    dst = instance_dir_new / FILE_TO_SAMPLE
    if src.exists():
        req_df = pd.read_csv(src, delimiter="\t")
        vehicle_size = sample_requests(req_df, sample_size, dst, start_time_str, duration_mins)

    # copy shapefile directory
    src = instance_dir_old / DIR_TO_COPY
    dst = instance_dir_new / DIR_TO_COPY
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)

    return vehicle_size

def generate_sampled_configs(cities, starts, starts_str, delays, delays_str, capacities, sample_sizes, methods):
    for start, durations in starts.items():
        start_str = f"{start:02d}-00"

        for (i, duration), (j, delay), city, capacity, sample_size in product(
            enumerate(durations), enumerate(delays), cities, capacities, sample_sizes
        ):
            print(f"\nSampling {int(sample_size*100)}% of the requests\n\n")
            # setup new instance config
            new_dir, new_config_path = setup_instance_paths(city, starts_str, start_str, i, delays_str, j, capacity, sample_size)

            # load old config
            old_dir, old_config_path = locate_old_config(city, starts_str, start_str, i)

            # modify config values
            old_config = load_instance_config(old_config_path)
            new_config = modify_configs(old_config, capacity, delay, sample_size)
            
            # generate new config
            generate_config(new_config, new_config_path)

            start_time_str = new_config['demand']['min_time']
            vehicle_size = sample_requests_and_copy_files(old_dir, new_dir, sample_size, start_time_str, duration)

            generate_vehicle_shapefiles(vehicle_size, new_config, old_dir, new_dir)

            # setup new results configs for sizing (IH)
            if SIZING:
                method = 'ih'
                results_dir = RESULTS_PATH_SIZING / f'{city}/start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[j]}/sample_{sample_size}/{method}'
                os.makedirs(results_dir, exist_ok=True)
                results_path = results_dir / "config.yaml"

                results_config = create_custom_results_config(str(new_config_path), method, str(results_dir))

                generate_config(results_config, results_path)
                vehicle_count = calculate_sizing_for_instance(results_path)
            else:
                vehicle_count = None

            # setup new instance configs for RCI
            setup_config_rci(vehicle_count, city, starts_str, start_str, i, j, capacity, delay, sample_size, methods, duration)

if __name__ == "__main__":
    cities = ['Manhattan']

    starts = {18: [5, 15, 30, 120]}
    starts_str = {'18-00': ['05_min', '15_min', '30_min', '2_h']}
    delays = [3, 5, 10, 15]
    delays_str = ['03_min', '05_min', '10_min', '15_min']
    capacities = [4, 6, 10]
    sample_range = [i/10 for i in range(1, 10)] + [i/4 for i in range(5, 9)]
    methods = ['ih', 'vga', 'halns', 'vga_chaining']

    capacities = [6, 10]
    sample_range = [i/10 for i in range(1, 7)]


    generate_sampled_configs(cities, starts, starts_str, delays, delays_str, capacities, sample_range, methods)
    # print(len(starts[18])*len(delays)*len(capacities)*len(sample_range)*len(methods))