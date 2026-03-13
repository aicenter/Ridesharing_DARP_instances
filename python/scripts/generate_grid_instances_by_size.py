"""
Generate grid-world DARP instances: one instance per grid size 2..10.

Parameters:
- size: 2, 3, 4, 5, 6, 7, 8, 9, 10
- requests: size^2 per instance
- max_request_start_time_s: 8 * 3600
- distance: 10
- max_delay: 480

Uses generate_requests_df from generate_grid_instances.py and writes
requests.csv plus config.yaml in each instance folder (e.g. size_2, size_3, ...).
"""
from pathlib import Path
import sys

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import numpy as np
import yaml
from generate_grid_instances import generate_requests_df


# Fixed parameters for all instances
# SIZES = [2, 3, 4, 5, 6, 7, 8, 9, 10]
SIZES = [25, 50, 75, 100, 125, 150, 175, 200]
MAX_DELAY = 300
SEED = 0
AVG_TRIP_TRAVEL_TIME = 900


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate 9 grid instances (one per size 2..10) with fixed parameters.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_scripts_dir / "grid_instances",
        help="Directory to write size_2 .. size_10 into",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help="Random seed for request generation",
    )
    args = parser.parse_args()
    out_root = args.output_dir
    seed = args.seed

    out_root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    for size in SIZES:
        n_requests = size * size
        max_request_start_time_s = n_requests / 200 * 3600
        distance = int(AVG_TRIP_TRAVEL_TIME * 3 / 2 / (size - 1))
        df = generate_requests_df(n_requests, max_request_start_time_s, size, rng)

        instance_dir = out_root / f"size_{size}"
        instance_dir.mkdir(parents=True, exist_ok=True)
        requests_path = instance_dir / "requests.csv"
        df.to_csv(requests_path, index=False)

        config = {
            "type": "grid",
            "size": size,
            "distance": distance,
            "demand": {
                "filepath": "./requests.csv",
                "min_time": 0,
                "max_time": max_request_start_time_s,
            },
            "max_travel_time_delay": {
                "mode": "absolute",
                "seconds": MAX_DELAY,
            },
            "vehicles": {
                "capital_cost": 400,
            },
        }
        config_path = instance_dir / "config.yaml"
        with open(config_path, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"  {instance_dir}: requests.csv ({n_requests} requests) + config.yaml")

    print(f"Done. {len(SIZES)} instances in {out_root}")


if __name__ == "__main__":
    main()
