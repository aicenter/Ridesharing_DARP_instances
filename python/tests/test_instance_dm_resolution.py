"""
Tests for the distance matrix resolution of the instance loader (#15):
- ``dm_filepath`` is used when set,
- otherwise ``<area_dir>/dm.h5``, falling back to ``<area_dir>/dm.csv``
  (the rule of the C++ instance reader),
- otherwise the Road Graph Tool rules (``<export.dir>/dm.{csv,h5}``),
- relative paths are resolved from the (absolute) config directory.
"""
import shutil
from pathlib import Path

import yaml

import darpinstances.instance
from darpinstances.instance import load_instance_config, resolve_instance_dm_filepath

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "basic"


def test_dm_filepath_takes_precedence_over_area_dir(tmp_path):
    (tmp_path / "dm.h5").touch()
    config = {"config_dir": tmp_path, "area_dir": ".", "dm_filepath": "./custom.csv"}
    assert resolve_instance_dm_filepath(config) == tmp_path / "custom.csv"


def test_area_dir_prefers_h5(tmp_path):
    area_dir = tmp_path / "area"
    instance_dir = area_dir / "instance"
    instance_dir.mkdir(parents=True)
    (area_dir / "dm.h5").touch()
    (area_dir / "dm.csv").touch()
    config = {"config_dir": instance_dir, "area_dir": ".."}
    assert resolve_instance_dm_filepath(config).resolve() == area_dir / "dm.h5"


def test_area_dir_falls_back_to_csv(tmp_path):
    area_dir = tmp_path / "area"
    instance_dir = area_dir / "instance"
    instance_dir.mkdir(parents=True)
    (area_dir / "dm.csv").touch()
    config = {"config_dir": instance_dir, "area_dir": ".."}
    assert resolve_instance_dm_filepath(config).resolve() == area_dir / "dm.csv"


def test_absolute_area_dir_is_kept(tmp_path):
    config = {"config_dir": tmp_path / "elsewhere", "area_dir": str(tmp_path)}
    assert resolve_instance_dm_filepath(config) == tmp_path / "dm.csv"


def test_without_area_dir_rgt_rules_apply(tmp_path):
    config = {"config_dir": tmp_path, "export": {"dir": "./export"}}
    assert resolve_instance_dm_filepath(config) == tmp_path / "export" / "dm.csv"


def test_load_instance_config_sets_absolute_config_dir(monkeypatch):
    monkeypatch.chdir(FIXTURE_DIR.parent)
    config = load_instance_config(Path("basic") / "config.yaml", set_defaults=False)
    assert Path(config["config_dir"]).is_absolute()
    assert Path(config["config_dir"]) == FIXTURE_DIR


def make_area_instance(root: Path) -> Path:
    """
    Instance layout of the published instances: the distance matrix is shared
    in the area directory, the instance config references it via area_dir.
    """
    area_dir = root / "area"
    instance_dir = area_dir / "instances" / "config_a"
    instance_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_DIR / "dm.csv", area_dir / "dm.csv")
    shutil.copy(FIXTURE_DIR / "requests.csv", instance_dir / "requests.csv")
    shutil.copy(FIXTURE_DIR / "vehicles.csv", instance_dir / "vehicles.csv")
    with open(FIXTURE_DIR / "config.yaml", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    del config["dm_filepath"]
    config["area_dir"] = "../../"
    config_path = instance_dir / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config, config_file)
    return config_path


def test_load_instance_with_area_dir(tmp_path):
    config_path = make_area_instance(tmp_path)
    instance, _ = darpinstances.instance.load_instance(config_path)
    assert instance.travel_time_provider.get_travel_time(0, 1) == 100
    assert len(instance.requests) == 2

