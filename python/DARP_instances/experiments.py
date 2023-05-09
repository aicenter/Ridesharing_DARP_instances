from typing import Dict, Optional, List, Tuple
import logging
import os
import yaml
import re
import pandas as pd
from pathlib import PurePath

import darpbenchmark.exec
import darpbenchmark.log
from darpbenchmark.inout import check_file_exists

from darpbenchmark.inout import check_file_exists


def call_experiment_runner_plain(params: Dict[str, str], timeout: Optional[int] = None) -> bool:
    commands = [
        "DARP-benchmark"
    ]

    for param_name, param_value in params.items():

        # add - and -- sign if omitted
        if not param_name.startswith("-"):
            param_name = f"-{param_name}" if len(param_name) == 1 else f"--{param_name}"

        commands.append(param_name)
        if param_value != True:
            commands.append(param_value)

    commands = [str(arg) for arg in commands]

    return darpbenchmark.exec.call_executable(commands, timeout)


def call_experiment_runner(
        instance_path: str,
        output_path: str,
        method_params: Dict[str, str],
        dm_path: Optional[str] = None,
        node_type: str = "amodsim"
) -> bool:
    params = {
        "-i": instance_path,
        "-o": output_path,
        "-t": node_type
    }
    if dm_path:
        params['-d'] = dm_path
    # params.extend([str(param) for item in method_params.items() for param in item])

    return call_experiment_runner_plain(params | method_params)


def run_experiments(instance_paths: List[str], dm_path: str, methods: Dict, out_path_base: str, exp_count: int = 1):
    fail = False
    for instance_path in instance_paths:
        if fail:
            break
        instance_path_parts = os.path.normpath(instance_path).split(os.path.sep)
        out_path = f"{out_path_base}/{instance_path_parts[-2]}-{instance_path_parts[-1]}/"

        for method_configuration_name, method_config in methods.items():
            if not fail:
                logging.info("running experiments for method %s", method_configuration_name)
                for run in range(0, exp_count):
                    out_path_run = f"{out_path}/{method_configuration_name}-{run}"
                    result = call_experiment_runner(instance_path, out_path_run, method_config, dm_path)

                    if not result:
                        fail = True
                        break


def load_experiment_config(path: str):
    logging.info(f"Loading experiment config from {path}")
    with open(path, 'r') as config_file:
        try:
            config = yaml.safe_load(config_file)

            # check the file locations and make them absolute
            os.chdir(os.path.dirname(path))
            check_file_exists(config['instance'])
            config['instance'] = os.path.abspath(config['instance'])

            # if outdir is set in config, check that that it is correct
            if "outdir" in config:
                check_file_exists(config['outdir'])
                config['outdir'] = os.path.abspath(config['outdir'])
            # othervise use the config file directory as outpath
            else:
                config['outdir'] = os.path.dirname(path)

            return config
        except yaml.YAMLError as er:
            logging.error(er)
            return False


def run_experiment_using_config(path: str, timeout: Optional[int] = None) -> bool:
    config = load_experiment_config(path)
    # instance_filename = os.path.normpath(config["instance"]).split(os.sep)[-1]
    if 'timeout' in config:
        if timeout:
            timeout = min(timeout, config['timeout'])
        else:
            timeout = config['timeout']
        del config['timeout']

    solution_path = None
    for filepath in os.listdir(config['outdir']):
        if filepath.endswith('solution.json'):
            solution_path = filepath
    # solution_path = f"{config['outdir']}/{instance_filename}-solution.json"

    # if os.path.exists(solution_path):

    if solution_path is None:
        return call_experiment_runner_plain(config, timeout)
    else:
        logging.info("The solution already exists ('%s')", solution_path)
        return True


def write_experiment_config(path: str, params: dict):
    logging.info('Saving config to %s', path)
    with open(path, 'w') as outfile:
        yaml.safe_dump(params, outfile)


def generate_experiment_configs_for_instance(
        full_result_root_dir,
        methods: Dict[str, dict],
        instance_path: PurePath
):
    # create root dir for all methods solving a single instance
    os.makedirs(full_result_root_dir, exist_ok=True)

    for method_name, method_config in methods.items():
        # create dir for method
        method_dir_full = os.path.join(full_result_root_dir, method_name)
        os.makedirs(method_dir_full, exist_ok=True)

        experiment_config_path = os.path.join(method_dir_full, "config.yaml")

        instance_rel_path = PurePath(os.path.relpath(instance_path, method_dir_full))

        config = {"instance": str(instance_rel_path.as_posix()), "outdir": '.'} | method_config
        DARP_instances.experiments.write_experiment_config(experiment_config_path, config)


def generate_experiments_config_for_instance_series(
        full_instance_root_path: PurePath,
        results_root_path: PurePath,
        methods: Dict[str, dict]
):
    """
    Generates experiment configuration files for a series of instances in a dir.
    :param full_instance_root_path: Path to the root folder of all instances from the series
    :param results_root_path:
    :param methods:
    :return:
    """

    if not os.path.exists(full_instance_root_path):
        logging.error(f"Instance root path is invalid: {full_instance_root_path} (absolute: {os.path.abspath(full_instance_root_path)})")
        raise FileNotFoundError

    for file in os.listdir(full_instance_root_path):
        filename = os.fsdecode(file)
        full_filepath = os.path.join(full_instance_root_path, filename)
        if os.path.isdir(full_filepath):

            # determine the instance path
            instance_path = None
            for file_in_inst_dir in os.listdir(full_filepath):
                filename_in_inst_dir = os.fsdecode(file_in_inst_dir)
                # print(filename)
                if filename_in_inst_dir.endswith("yaml"):
                    results_instance_dir = os.path.join(results_root_path, filename)
                    instance_folder_path = full_instance_root_path / PurePath(filename)
                    instance_path = instance_folder_path / PurePath(filename_in_inst_dir)
                    break
            if instance_path is None:
                raise Exception(f"Instance file not found in dir: {full_filepath}")


            generate_experiment_configs_for_instance(results_instance_dir, methods, instance_path)


def run_experiment_configs_in_dir(
        dir_path: str,
        sort_params: Optional[List[Tuple[str, int]]] = None,
        ignore_methods: Optional[List[str]] = None,
        timeout: Optional[int] = None
) -> bool:
    """
    Runs experiment for all configurations in dir. It is recursive, i.e., it follows subdirectories.
    Folder names starting with underscore are ignored. Also, if the solution is found for a configuration,
    the configuration is skipped.
    @param dir_path: path to the root dir
    @param sort_params: optional sort parameter to run experiments in a specific order.
    @param ignore_methods: list of methods to be ignored
    @param timeout in seconds
    @return: True in case of success, otherwise False
    """
    result = True

    experiments = search_experiments_in_dir(dir_path, ignore_methods)

    # df column labels
    columns = ["exp_path"]
    if sort_params is not None:
        for param in sort_params:
            columns.append(param[0])

    # exp df creation
    exp_processed = []
    for exp_path in experiments:
        exp = [exp_path]

        if sort_params is not None:
            for param in sort_params:
                name = param[0]
                param_name = f"{name}_(\\d+)"
                sr = re.search(param_name, exp_path)
                value = int(sr.group(1))
                exp.append(value)

        exp_processed.append(exp)

    df = pd.DataFrame(exp_processed, columns=columns)

    # sort if there are any params
    df["sort"] = 0
    if sort_params is not None:
        for param in sort_params:
            name = param[0]
            coeff = 1 if len(param) == 1 else param[1]
            df['sort'] = df['sort'] + df[name] * coeff

    df.sort_values('sort', inplace=True)

    # run the experiments
    for exp_path in df['exp_path']:
        result = run_experiment_using_config(exp_path, timeout)
        if not result:
            break

    return result


def search_experiments_in_dir(dir_path: str, ignore_methods: Optional[List[str]] = None) -> List[str]:
    experiments = []

    for file in os.listdir(dir_path):
        filename = os.fsdecode(file)
        filepath = os.path.join(dir_path, filename)

        if os.path.isdir(filepath) and not filename.startswith("_") \
                and (ignore_methods is None or filename not in ignore_methods):
            subdir_experiments = search_experiments_in_dir(filepath, ignore_methods)
            experiments.extend(subdir_experiments)
        elif filename.endswith("yaml"):
            experiments.append(filepath)

    return experiments
