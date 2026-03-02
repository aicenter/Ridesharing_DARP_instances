"""
Generate fleet-sizing config files for Kronmueller 2024 grid instances.

Creates config files for each parameter combination in instance_0 .. instance_4.
Uses existing requests.csv in each instance dir; does NOT generate requests.

Parameters:
  - max_travel_time_delay (seconds): 0, 480
  - vehicle_capital_cost: 400, 600, 800

Output: 6 config files per instance (config_delay{N}_vcc{M}.yaml)
"""
from pathlib import Path
import yaml


ROOT = Path(r"C:\Google Drive AIC\My Drive\AIC Experiment Data\Fleet-sizing\kronmueller_2024_grid_instances\Instances")
MAX_TRAVEL_TIME_DELAYS = [0, 480]
VEHICLE_CAPITAL_COSTS = [400, 600, 800]
N_INSTANCES = 5  # instance_0 .. instance_4

# Base config (matches format in reference config.yaml)
BASE_CONFIG = {
    "type": "grid",
    "size": 40,
    "distance": 10,
    "demand": {
        "filepath": "./requests.csv",
        "min_time": 0,
        "max_time": 28800,
    },
}


def main() -> None:
    for i in range(N_INSTANCES):
        instance_dir = ROOT / f"instance_{i}"
        requests_path = instance_dir / "requests.csv"
        if not requests_path.exists():
            raise FileNotFoundError(f"Expected {requests_path} - requests.csv must exist (no generation)")

        for delay in MAX_TRAVEL_TIME_DELAYS:
            for vehicle_capital_cost in VEHICLE_CAPITAL_COSTS:
                config = {
                    **BASE_CONFIG,
                    "max_travel_time_delay": {"mode": "absolute", "seconds": delay},
                    "vehicles": { "capital_cost": vehicle_capital_cost},
                }
                config_name = f"config-max_delay_{delay}_s-vehicle_cost_{vehicle_capital_cost}.yaml"
                config_path = instance_dir / config_name
                with open(config_path, "w") as f:
                    yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
                print(f"  {instance_dir.name}/{config_name}")

    print(f"Done. {N_INSTANCES} instances × {len(MAX_TRAVEL_TIME_DELAYS)} delays × {len(VEHICLE_CAPITAL_COSTS)} vcc = {N_INSTANCES * len(MAX_TRAVEL_TIME_DELAYS) * len(VEHICLE_CAPITAL_COSTS)} configs in {ROOT}")


if __name__ == "__main__":
    main()
