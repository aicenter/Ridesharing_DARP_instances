"""
Tests of the online mode of the instance config (``online_mode`` section): parsing, defaults and validation.
"""
from pathlib import Path

import pytest

import darpinstances.solution_checker
from darpinstances.instance import OnlineMode, load_online_mode

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "online"


def test_online_mode_absent_is_off():
    online_mode = load_online_mode({'max_delay': {'mode': 'absolute', 'seconds': 300}})
    assert online_mode == OnlineMode()
    assert not online_mode.on
    assert online_mode.batch_period == 0
    assert not online_mode.allow_delay_promised_pickup


def test_online_mode_parsed():
    online_mode = load_online_mode({'online_mode': {'on': True, 'batch_period': 30}})
    assert online_mode == OnlineMode(on=True, batch_period=30, allow_delay_promised_pickup=False)

    allowing = load_online_mode({'online_mode': {'on': True, 'batch_period': 60, 'allow_delay_promised_pickup': True}})
    assert allowing.allow_delay_promised_pickup

    # the batch period is only required when the mode is on
    assert not load_online_mode({'online_mode': {'on': False, 'batch_period': 30}}).on


def test_online_mode_requires_the_batch_period():
    with pytest.raises(ValueError):
        load_online_mode({'online_mode': {'on': True}})
    with pytest.raises(ValueError):
        load_online_mode({'online_mode': {'on': True, 'batch_period': 0}})


def test_online_mode_unknown_key():
    with pytest.raises(ValueError):
        load_online_mode({'online_mode': {'on': True, 'batch_period': 30, 'period': 30}})
    with pytest.raises(ValueError):
        load_online_mode({'online_mode': True})


def test_instance_loads_the_online_mode():
    instance, _, _ = darpinstances.solution_checker.load_instance(FIXTURE_DIR / "config.yaml")
    online_mode = instance.darp_instance_config.online_mode
    assert online_mode == OnlineMode(on=True, batch_period=30)
    # the pickup delay of the instance is still applied
    assert instance.darp_instance_config.max_pickup_delay == 120
