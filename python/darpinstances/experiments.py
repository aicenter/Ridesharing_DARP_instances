from typing import Dict, Optional, List, Tuple, Union
import logging
import os
import yaml
import re
import pandas as pd
from pathlib import PurePath, Path

import darpinstances.exec
import darpinstances.log
from darpinstances.inout import check_file_exists

from darpinstances.inout import check_file_exists


def load_experiment_config(path: Union[str,Path]):
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


def write_experiment_config(path: str, params: dict):
    logging.info('Saving config to %s', path)
    with open(path, 'w') as outfile:
        yaml.safe_dump(params, outfile)


def generate_experiment_configs_for_instance(
    full_result_root_dir: Path,
    methods: Dict[str, dict],
    instance_path: PurePath,
    overwrite: bool = True
):
    # create root dir for all methods solving a single instance
    os.makedirs(full_result_root_dir, exist_ok=True)

    for method_name, method_config in methods.items():
        # create dir for method
        method_dir_full = full_result_root_dir / method_name
        os.makedirs(method_dir_full, exist_ok=True)

        experiment_config_path = method_dir_full / "config.yaml"

        instance_rel_path = PurePath(os.path.relpath(instance_path, method_dir_full))

        config = {"instance": str(instance_rel_path.as_posix()), "outdir": '.'} | method_config

        if overwrite or not experiment_config_path.exists():
            darpinstances.experiments.write_experiment_config(experiment_config_path, config)
        else:
            logging.info(f"Skipping config generation for {experiment_config_path} as it already exists")


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
