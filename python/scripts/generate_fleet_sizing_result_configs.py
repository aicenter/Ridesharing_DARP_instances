"""
Generate solution/experiment configurations for Kronmueller 2024 fleet-sizing results.

Creates Results/instance_{i}/delay_{delay}/vcc_{vcc}/kronmueller_2024/config.yaml
for each instance and parameter combination, pointing to the corresponding
instance config.

Structure:
  Results/
    instance_0/
      delay_0/
        vcc_400/kronmueller_2024/config.yaml  -> Instances/instance_0/config-max_delay_0_s-vehicle_cost_400.yaml
        vcc_600/kronmueller_2024/config.yaml
        vcc_800/kronmueller_2024/config.yaml
      delay_480/
        vcc_400/kronmueller_2024/config.yaml
        ...
"""
import os
from pathlib import Path

import darpinstances.experiments

BASE = Path(r"C:\Google Drive AIC\My Drive\AIC Experiment Data\Fleet-sizing\kronmueller_2024_grid_instances")
INSTANCES_ROOT = BASE / "Instances"
RESULTS_ROOT = BASE / "Results"
METHOD_NAME = "kronmueller_2024"

MAX_TRAVEL_TIME_DELAYS = [0, 480]
VEHICLE_CAPITAL_COSTS = [400, 600, 800]
N_INSTANCES = 5  # instance_0 .. instance_4

# Instance config filename (must match generate_fleet_sizing_configs.py)
def instance_config_name(delay: int, vcc: int) -> str:
    return f"config-max_delay_{delay}_s-vehicle_cost_{vcc}.yaml"


def main(overwrite: bool = True) -> None:
    method_config = {}  # fleet-sizing / kronmueller_2024; extend if needed

    for i in range(N_INSTANCES):
        instance_dir = INSTANCES_ROOT / f"instance_{i}"

        for delay in MAX_TRAVEL_TIME_DELAYS:
            for vehicle_capital_cost in VEHICLE_CAPITAL_COSTS:
                config_name = instance_config_name(delay, vehicle_capital_cost)
                instance_config_path = instance_dir / config_name
                if not instance_config_path.exists():
                    raise FileNotFoundError(
                        f"Instance config not found: {instance_config_path}. "
                        "Run generate_fleet_sizing_configs.py first."
                    )

                method_dir = RESULTS_ROOT / f"instance_{i}" / f"max_delay_{delay}_s" / f"vehicle_capital_cost_{vehicle_capital_cost}" / METHOD_NAME
                darpinstances.experiments.generate_experiment_config(
                    method_dir, method_config, instance_config_path, overwrite=overwrite
                )
                print(f"  {method_dir.relative_to(RESULTS_ROOT)}/config.yaml")

    n = N_INSTANCES * len(MAX_TRAVEL_TIME_DELAYS) * len(VEHICLE_CAPITAL_COSTS)
    print(f"Done. {n} experiment configs in {RESULTS_ROOT}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate fleet-sizing result configs for Kronmueller 2024 grid instances.")
    parser.add_argument("--no-overwrite", action="store_true", help="Skip configs that already exist")
    args = parser.parse_args()
    main(overwrite=not args.no_overwrite)
