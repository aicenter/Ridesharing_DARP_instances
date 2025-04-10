import os
import json
import logging
import csv
import pkgutil
import numpy as np
import h5py
from pathlib import Path

from typing import Tuple, Dict, Iterable, Union, List

import yaml

import darpinstances.log


def load_csv(filepath: Union[str, Path], delimiter: str = ",") -> Iterable:
	logging.info("Loading csv file from:  %s", os.path.realpath(filepath))
	f = open(filepath, "r")
	return csv.reader(f, delimiter=delimiter)


def load_json(filepath: Union[str, Path]) -> Union[Dict, List]:
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


def check_file_exists(path: Union[str,Path], raise_ex: bool = True) -> bool:
	if isinstance(path, str):
		path = Path(path)

	if not path.exists() and not path.is_dir():
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


def load_yaml(path: Path):
	with open(path, "r") as stream:
		try:
			py_yaml = yaml.safe_load(stream)
		except yaml.YAMLError as exc:
			logging.error(exc)
	return py_yaml
