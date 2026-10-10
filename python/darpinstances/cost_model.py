"""
Generalized weighted cost model of a DARP solution.

The cost of a plan is a weighted sum of *components*. Each component is
declared once in :data:`COST_COMPONENTS`; the declaration drives the
``cost:`` section of the instance config (key names, defaults, legacy
fallbacks), the accumulators of the solution checker, the final sum, the
``cost_components`` breakdown of solution files and the schema sync tests.

To add a component: add a :class:`CostComponent` here, accumulate its raw
quantity in ``SolutionChecker.check_plan`` (``raw[<key>] += ...``), add its
key to ``JSON/cost_components.schema.json``, and document it in the README
(the "Adding a cost component" checklist there lists the complete steps).

The cost of a plan is

    cost = Σ_components weight * raw quantity          (PER_LEG, PER_DROP_OFF, PER_PLAN)
         + Σ_constants weight                          (CONSTANT, non-empty plans only)

and the cost of a solution is the sum of its plan costs. The defaults
reproduce the original DARP cost exactly: total travel time, plus drop-off
delay weighted by the legacy ``demand.relative_delay_cost``, plus the legacy
``vehicles.capital_cost`` per non-empty plan.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Tuple


class Measure(Enum):
    """How the raw quantity of a component is accumulated over a plan."""

    PER_LEG = "per_leg"  # on every driven leg (incl. accepted late arrival and the priced depot return)
    PER_DROP_OFF = "per_drop_off"  # once per drop-off action
    PER_PLAN = "per_plan"  # one quantity derived from the whole plan (e.g. its duration)
    CONSTANT = "constant"  # the weight itself is the contribution of a non-empty plan


ACCOUNTING_MODES = ("per_traveller", "per_request")


@dataclass(frozen=True)
class CostComponent:
    key: str  # component key: accumulator name and key in `cost_components` ("travel_time")
    weight_key: str  # key under `cost:` in config.yaml ("travel_time_weight")
    unit: str  # unit of the raw quantity ("s", "m", "passenger-s", "plan")
    default: float
    measure: Measure
    legacy_source: Optional[Tuple[str, str]] = None  # (section, key) of the legacy config fallback
    accounting_sensitive: bool = False  # scaled by the travellers under per_traveller accounting
    description: str = ""


COST_COMPONENTS: Tuple[CostComponent, ...] = (
    CostComponent(
        "travel_time", "travel_time_weight", "s", 1.0, Measure.PER_LEG,
        description="vehicle travel time, including accepted late arrivals and the priced depot return",
    ),
    CostComponent(
        "distance", "distance_weight", "m", 0.0, Measure.PER_LEG,
        description="vehicle travel distance; requires dist_filepath",
    ),
    CostComponent(
        "ride_time", "ride_time_weight", "passenger-s", 0.0, Measure.PER_DROP_OFF,
        accounting_sensitive=True,
        description="ride from the pickup departure to the drop-off arrival",
    ),
    CostComponent(
        "passenger_delay", "passenger_delay_weight", "passenger-s", 0.0, Measure.PER_DROP_OFF,
        legacy_source=("demand", "relative_delay_cost"), accounting_sensitive=True,
        description="drop-off delay versus the ideal direct ride starting at the desired pickup time",
    ),
    CostComponent(
        "earliness", "earliness_weight", "s", 0.0, Measure.PER_DROP_OFF,
        description="arrival before required_arrival_time",
    ),
    CostComponent(
        "plan_duration", "plan_duration_weight", "s", 0.0, Measure.PER_PLAN,
        description="plan departure to the end of the last action or the depot return; 0 for empty plans",
    ),
    CostComponent(
        "fixed_plan", "fixed_plan_cost", "plan", 0.0, Measure.CONSTANT,
        description="constant per non-empty plan",
    ),
    CostComponent(
        "vehicle_capital", "vehicle_capital_cost", "plan", 0.0, Measure.CONSTANT,
        legacy_source=("vehicles", "capital_cost"),
        description="constant per non-empty plan (the legacy vehicle capital cost)",
    ),
)

COMPONENTS_BY_KEY: Dict[str, CostComponent] = {c.key: c for c in COST_COMPONENTS}
COMPONENTS_BY_WEIGHT_KEY: Dict[str, CostComponent] = {c.weight_key: c for c in COST_COMPONENTS}
COST_CONFIG_KEYS = frozenset(COMPONENTS_BY_WEIGHT_KEY) | {"accounting"}
MEASURED_COMPONENT_KEYS = tuple(c.key for c in COST_COMPONENTS if c.measure is not Measure.CONSTANT)

# absolute tolerance of the plan / solution cost checks (legacy solvers write integer costs)
COST_TOLERANCE = 1.0


def _as_weight(weight_key: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Cost weight '{weight_key}' must be a number, got: {value!r}")
    return float(value)


class CostWeights:
    """
    Weights of the generalized solution cost model, one attribute per
    component weight key (``cost_weights.travel_time_weight`` etc.) plus the
    ``accounting`` mode:

    - ``per_traveller`` (default, legacy): ride time and drop-off delay are
      multiplied by the request's total travellers, and the delay is measured
      from the desired pickup time (it includes the rider's own boarding
      service time),
    - ``per_request`` (allocator-style): ride time and delay are counted once
      per request, and the delay is measured from the pickup DEPARTURE (net of
      the boarding service time).
    """

    def __init__(self, accounting: str = "per_traveller", **weights: float):
        unknown = set(weights) - set(COMPONENTS_BY_WEIGHT_KEY)
        if unknown:
            raise ValueError(
                f"Unknown cost weights: {sorted(unknown)}; known weights: {sorted(COMPONENTS_BY_WEIGHT_KEY)}"
            )
        for component in COST_COMPONENTS:
            value = weights.get(component.weight_key, component.default)
            setattr(self, component.weight_key, _as_weight(component.weight_key, value))
        if accounting not in ACCOUNTING_MODES:
            raise ValueError(f"Unknown cost accounting mode: {accounting}")
        self.accounting = accounting

    @classmethod
    def from_config(cls, instance_config: Mapping) -> "CostWeights":
        """
        Weights from the ``cost:`` section of an instance config, with the
        legacy fallbacks (``demand.relative_delay_cost``,
        ``vehicles.capital_cost``) as defaults of the corresponding weights.
        Raises ValueError on an unknown key under ``cost:``.
        """
        cost_config = instance_config.get("cost") or {}
        if not isinstance(cost_config, Mapping):
            raise ValueError(f"The 'cost' section of the instance config must be a mapping, got: {cost_config!r}")
        unknown = set(cost_config) - COST_CONFIG_KEYS
        if unknown:
            raise ValueError(
                f"Unknown keys in the 'cost' section of the instance config: {sorted(unknown)}; "
                f"known keys: {sorted(COST_CONFIG_KEYS)}"
            )
        weights = {}
        for component in COST_COMPONENTS:
            value = cost_config.get(component.weight_key)
            if value is None and component.legacy_source is not None:
                section, key = component.legacy_source
                value = (instance_config.get(section) or {}).get(key)
            weights[component.weight_key] = component.default if value is None else value
        return cls(accounting=cost_config.get("accounting", "per_traveller"), **weights)

    def weight(self, key: str) -> float:
        """Weight of the component with the given component key."""
        return getattr(self, COMPONENTS_BY_KEY[key].weight_key)

    def as_dict(self) -> Dict[str, float]:
        """Weight key -> value, for logging and verdicts."""
        return {c.weight_key: getattr(self, c.weight_key) for c in COST_COMPONENTS}

    def contributions(self, raw: Mapping[str, float], non_empty_plan: bool) -> Dict[str, float]:
        """
        Weighted contribution of every component (component key -> value).
        Measured components use their raw quantity (missing = 0); CONSTANT
        components contribute their weight for non-empty plans only.
        """
        result = {}
        for component in COST_COMPONENTS:
            weight = getattr(self, component.weight_key)
            if component.measure is Measure.CONSTANT:
                result[component.key] = weight if non_empty_plan else 0.0
            else:
                result[component.key] = weight * float(raw.get(component.key, 0.0))
        return result

    def total(self, raw: Mapping[str, float], non_empty_plan: bool) -> float:
        return sum(self.contributions(raw, non_empty_plan).values())

    def describe(self, raw: Mapping[str, float], non_empty_plan: bool) -> str:
        """Human-readable breakdown ``travel_time 420.0 (420.0 s x 1.0) + ...`` of the non-zero terms."""
        terms = []
        for component in COST_COMPONENTS:
            weight = getattr(self, component.weight_key)
            if weight == 0:
                continue
            if component.measure is Measure.CONSTANT:
                if non_empty_plan:
                    terms.append(f"{component.key} {weight}")
            else:
                quantity = float(raw.get(component.key, 0.0))
                terms.append(f"{component.key} {weight * quantity} ({quantity} {component.unit} x {weight})")
        return " + ".join(terms) if terms else "0"

    def __repr__(self) -> str:
        return f"CostWeights({self.as_dict()}, accounting={self.accounting!r})"


def sum_contributions(breakdowns: Iterable[Mapping[str, float]]) -> Dict[str, float]:
    """Component-wise sum of several breakdowns (component key -> value)."""
    total = {c.key: 0.0 for c in COST_COMPONENTS}
    for breakdown in breakdowns:
        for key, value in breakdown.items():
            total[key] = total.get(key, 0.0) + value
    return total
