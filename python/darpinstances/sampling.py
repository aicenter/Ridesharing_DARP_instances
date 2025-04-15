import os
from pathlib import Path
import pandas as pd
from itertools import product
import shutil

from darpinstances.instance import load_instance_config
from darpinstances.instance_generation.generate_config import generate_config
from darpbenchmark.sizing import calculate_sizing_for_instance
from darpinstances.instance_generation.map import NearestNodeProvider, get_map
from darpinstances.instance_generation.demand_generation import generate_demand
from darpinstances.instance_generation.vehicles import generate_vehicles


PATH = Path.cwd()
INSTANCE_PATH_OLD = PATH.parents[0] / "Instances"
INSTANCE_PATH_RCI = PATH.parents[0] / "rci" / "Instances"
RESULTS_PATH = PATH.parents[0] / "sizing" / "Results"
RESULTS_PATH_RCI = PATH.parents[0] / "rci" / "Results"


def create_custom_results_config(instance_path, method, outdir):
    config = {}
    config['instance'] = instance_path
    config['method'] = method
    config['outdir'] = outdir
    return config

def setup_config_rci(vehicle_count, city, start_str, i, j, capacity, delay, sample_size):
    # setup new instance config
    instance_path_relative = Path(f'{city}/instances/start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[j]}/sample_{sample_size}')
    instance_dir_new = INSTANCE_PATH_RCI / instance_path_relative
    instance_path = instance_dir_new / "config.yaml"
    os.makedirs(instance_dir_new, exist_ok=True)

    # load old config
    instance_dir_old = INSTANCE_PATH_OLD / instance_path_relative
    instance_config_path = instance_dir_old / 'config.yaml'

    inst_conf_dict = load_instance_config(instance_config_path)
    instance_config = modify_configs(inst_conf_dict, capacity, delay)
    if vehicle_count:
        instance_config['vehicles']['vehicle_count'] = vehicle_count

    # generate new config
    generate_config(instance_config, instance_path)

    # copy requests and vehicles
    files = ['requests.csv', 'vehicles.csv']
    for f in files:
        src = instance_dir_old / f
        dst = instance_dir_new / f
        if src.exists():
            shutil.copy(src, dst)

    # setup new results configs
    for method in methods:

        results_dir = RESULTS_PATH_RCI / f'{city}/start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[j]}/sample_{sample_size}/{method}'
        os.makedirs(results_dir, exist_ok=True)
        results_path = results_dir / "config.yaml"

        if rci:
            instance_path =  'Instances' / instance_path_relative / 'config.yaml'
            results_dir = f'Results/{city}/start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[j]}/sample_{sample_size}/{method}'
        
        results_config = create_custom_results_config(str(instance_path), method, str(results_dir))

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

def modify_configs(instance_config, capacity, delay):
    instance_config['vehicles']['vehicle_capacity'] = capacity
    instance_config['demand']['filepath'] = 'requests.csv'
    instance_config['max_prolongation'] = delay*60
    instance_config['area_dir'] = "../../../../../"
    instance_config['vehicles'].pop('vehicle_count', None)
    instance_config['map'].pop('path', None)
    instance_config.pop('instance_dir', None)
    return instance_config

def sample_requests(req_df, sample_size, destination_file) -> int:
    if len(req_df.columns) == 4:
        req_df = req_df.iloc[:, :-1]
    sample_size = int(len(req_df) * sample_size)
    sampled_df = req_df.sample(n=sample_size, random_state=1)
    sampled_df.reset_index(drop=True, inplace=True)
    sampled_df.to_csv(destination_file, index=False, sep='\t')
    return len(sampled_df)

def generate_sampled_configs(sample_size):
    for start, durations in starts.items():
        start_str = f"{start:02d}-00"

        for (i, duration), (j, delay), city, capacity in product(
            enumerate(durations), enumerate(delays), cities, capacities
        ):
            
            # setup new instance config
            instance_path_relative = Path(f'{city}/instances/start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[j]}/sample_{sample_size}')
            instance_dir_new = INSTANCE_PATH_OLD / instance_path_relative
            instance_path = instance_dir_new / "config.yaml"

            # load old config
            instance_dir_old = INSTANCE_PATH_OLD / f'{city}/instances/start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[0]}'
            instance_config_path = instance_dir_old / 'config.yaml'
            if not instance_config_path.exists() and starts_str[start_str][i] == '2_h':
                instance_dir_old = INSTANCE_PATH_OLD / f'{city}/instances/start_{start_str}/duration_02_h/max_delay_{delays_str[0]}'
                instance_config_path = instance_dir_old / 'config.yaml'
                
            # modify config values
            inst_conf_dict = load_instance_config(instance_config_path)
            instance_config = modify_configs(inst_conf_dict, capacity, delay)
            
            os.makedirs(instance_dir_new, exist_ok=True)

            # generate new config
            generate_config(instance_config, instance_path)

            # INSTEAD of copying the requests and vehicles, we will sample from them
            f = 'requests.csv'
            src = instance_dir_old / f
            dst = instance_dir_new / f
            if src.exists():
                req_df = pd.read_csv(src, delimiter='\t')
                vehicle_size = sample_requests(req_df, sample_size, dst)
            
            # copy shapefile directory
            src = instance_dir_old / dir_copy
            dst = instance_dir_new / dir_copy
            if src.exists():
                shutil.copytree(src, dst, dirs_exist_ok=True)

            generate_vehicle_shapefiles(vehicle_size, instance_config, instance_dir_old, instance_dir_new)

            # setup new results configs for sizing (IH)
            if sizing:
                method = 'ih'
                results_dir = RESULTS_PATH / f'{city}/start_{start_str}/duration_{starts_str[start_str][i]}/max_delay_{delays_str[j]}/sample_{sample_size}/{method}'
                os.makedirs(results_dir, exist_ok=True)
                results_path = results_dir / "config.yaml"

                results_config = create_custom_results_config(str(instance_path), method, str(results_dir))

                generate_config(results_config, results_path)
                vehicle_count = calculate_sizing_for_instance(results_path)
            else:
                vehicle_count = None

            # setup new instance configs for RCI
            setup_config_rci(vehicle_count, city, start_str, i, j, capacity, delay, sample_size)

cities = ['Manhattan']
# starts = {18: [5]}
# starts_str = {'18-00': ['05_min']}
# delays = [3]
# delays_str = ['03_min']
capacities = [4]
# methods = ['ih']
starts = {18: [5, 15, 30, 120]}
starts_str = {'18-00': ['05_min', '15_min', '30_min', '2_h']}
delays = [3, 5, 10, 15]
delays_str = ['03_min', '05_min', '10_min', '15_min']
# capacities = [4, 6, 10]
methods = ['ih', 'vga', 'halns', 'vga_chaining']


file_copy = 'requests.csv'
dir_copy = 'shapefiles'

rci = True
sizing = False
sample_range = [i/10 for i in range(1, 10)]
for sample_percent in sample_range:
    print(f"Sampling {int(sample_percent*100)}% of the requests\n")
    generate_sampled_configs(sample_percent)