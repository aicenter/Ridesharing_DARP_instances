"""
Tests of the cost component registry (darpinstances.cost_model): CostWeights
construction and loading with legacy fallbacks, the weighted contributions,
and the sync between the registry and the JSON schemas.
"""
import json
from pathlib import Path

import pytest

from darpinstances.cost_model import (
    COMPONENTS_BY_KEY,
    COST_COMPONENTS,
    COST_CONFIG_KEYS,
    MEASURED_COMPONENT_KEYS,
    CostWeights,
    Measure,
    sum_contributions,
)

JSON_DIR = Path(__file__).resolve().parents[2] / "JSON"

# raw quantities of the extended fixture's valid solution (see test_unified_format.py)
EXTENDED_RAW = {
    "travel_time": 420,
    "distance": 4200,
    "ride_time": 820,
    "passenger_delay": 320,
    "earliness": 240,
    "plan_duration": 470,
}
EXTENDED_WEIGHTS = dict(
    travel_time_weight=1.0,
    distance_weight=0.01,
    ride_time_weight=0.5,
    passenger_delay_weight=0.2,
    earliness_weight=0.1,
    plan_duration_weight=0.05,
    fixed_plan_cost=10,
    vehicle_capital_cost=25,
)


def test_registry_integrity():
    keys = [c.key for c in COST_COMPONENTS]
    weight_keys = [c.weight_key for c in COST_COMPONENTS]
    assert len(set(keys)) == len(keys)
    assert len(set(weight_keys)) == len(weight_keys)
    assert set(MEASURED_COMPONENT_KEYS) == {c.key for c in COST_COMPONENTS if c.measure is not Measure.CONSTANT}
    legacy = {c.legacy_source for c in COST_COMPONENTS if c.legacy_source is not None}
    assert legacy == {("demand", "relative_delay_cost"), ("vehicles", "capital_cost")}
    assert "accounting" in COST_CONFIG_KEYS
    assert COST_CONFIG_KEYS - {"accounting"} == set(weight_keys)


def test_default_weights_are_the_legacy_cost():
    weights = CostWeights()
    assert weights.travel_time_weight == 1.0
    assert all(getattr(weights, c.weight_key) == 0.0 for c in COST_COMPONENTS if c.key != "travel_time")
    assert weights.accounting == "per_traveller"
    # legacy plan cost = travel time only
    assert weights.total({"travel_time": 420}, non_empty_plan=True) == 420


def test_unknown_weight_and_bad_values_rejected():
    with pytest.raises(ValueError, match="Unknown cost weights"):
        CostWeights(foo=1)
    with pytest.raises(ValueError, match="must be a number"):
        CostWeights(travel_time_weight=True)
    with pytest.raises(ValueError, match="must be a number"):
        CostWeights(travel_time_weight="1")
    with pytest.raises(ValueError, match="accounting"):
        CostWeights(accounting="per_vehicle")


def test_from_config_legacy_fallbacks():
    weights = CostWeights.from_config(
        {"demand": {"relative_delay_cost": 0.5}, "vehicles": {"capital_cost": 400}}
    )
    assert weights.passenger_delay_weight == 0.5
    assert weights.vehicle_capital_cost == 400.0
    assert weights.travel_time_weight == 1.0

    # null legacy values fall back to the defaults
    weights = CostWeights.from_config({"vehicles": {"capital_cost": None}, "demand": {}})
    assert weights.vehicle_capital_cost == 0.0

    # no config at all
    assert CostWeights.from_config({}).as_dict() == CostWeights().as_dict()


def test_from_config_cost_section_overrides_legacy():
    weights = CostWeights.from_config(
        {
            "demand": {"relative_delay_cost": 0.5},
            "vehicles": {"capital_cost": 400},
            "cost": {"passenger_delay_weight": 2, "vehicle_capital_cost": 7.5, "accounting": "per_request"},
        }
    )
    assert weights.passenger_delay_weight == 2.0
    assert weights.vehicle_capital_cost == 7.5
    assert weights.accounting == "per_request"


def test_from_config_unknown_key_rejected():
    with pytest.raises(ValueError) as error:
        CostWeights.from_config({"cost": {"foo": 1}})
    assert "foo" in str(error.value)
    assert "travel_time_weight" in str(error.value)
    with pytest.raises(ValueError, match="mapping"):
        CostWeights.from_config({"cost": 3})


def test_contributions_constants_only_for_non_empty_plans():
    weights = CostWeights(fixed_plan_cost=10, vehicle_capital_cost=25)
    empty = weights.contributions({}, non_empty_plan=False)
    assert empty["fixed_plan"] == 0.0
    assert empty["vehicle_capital"] == 0.0
    assert weights.total({}, non_empty_plan=False) == 0.0

    non_empty = weights.contributions({"travel_time": 100}, non_empty_plan=True)
    assert non_empty["fixed_plan"] == 10.0
    assert non_empty["vehicle_capital"] == 25.0
    assert non_empty["travel_time"] == 100.0
    assert weights.total({"travel_time": 100}, non_empty_plan=True) == 135.0


def test_extended_fixture_cost():
    weights = CostWeights(**EXTENDED_WEIGHTS)
    weighted = weights.contributions(EXTENDED_RAW, non_empty_plan=True)
    assert weighted["travel_time"] == pytest.approx(420)
    assert weighted["distance"] == pytest.approx(42)
    assert weighted["ride_time"] == pytest.approx(410)
    assert weighted["passenger_delay"] == pytest.approx(64)
    assert weighted["earliness"] == pytest.approx(24)
    assert weighted["plan_duration"] == pytest.approx(23.5)
    assert weighted["fixed_plan"] == 10
    assert weighted["vehicle_capital"] == 25
    assert weights.total(EXTENDED_RAW, non_empty_plan=True) == pytest.approx(1018.5)
    assert set(weighted) == set(COMPONENTS_BY_KEY)


def test_describe_and_weight_accessors():
    weights = CostWeights(**EXTENDED_WEIGHTS)
    assert weights.weight("passenger_delay") == 0.2
    description = weights.describe(EXTENDED_RAW, non_empty_plan=True)
    assert "travel_time 420.0 (420.0 s x 1.0)" in description
    assert "vehicle_capital 25.0" in description
    assert CostWeights().describe({"travel_time": 5}, non_empty_plan=True) == "travel_time 5.0 (5.0 s x 1.0)"


def test_sum_contributions():
    total = sum_contributions([{"travel_time": 1.0, "fixed_plan": 10.0}, {"travel_time": 2.5}])
    assert total["travel_time"] == 3.5
    assert total["fixed_plan"] == 10.0
    assert total["distance"] == 0.0


def test_cost_components_schema_matches_registry():
    schema = json.loads((JSON_DIR / "cost_components.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(COMPONENTS_BY_KEY)
    assert all(prop["type"] == "number" for prop in schema["properties"].values())


@pytest.mark.parametrize("schema_name", ["solution.schema.json", "vehicle_plan.schema.json"])
def test_cost_is_a_number_in_the_solution_schemas(schema_name):
    schema = json.loads((JSON_DIR / schema_name).read_text(encoding="utf-8"))
    assert schema["properties"]["cost"]["type"] == "number"
    assert schema["properties"]["cost_components"]["$ref"] == "cost_components.schema.json"
    assert "cost" in schema["required"]
    assert "cost_components" not in schema["required"]
