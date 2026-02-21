"""
Generate 5 grid-world DARP instances with the same parameters as in:

  Kronmueller et al. (2024), "Reducing the Minimal Fleet Size by Delaying
  Individual Tasks", IEEE Trans. Intelligent Transportation Systems.

Section V-B (Gridworld): n=40, b=10, |T|=1600, tasks start in [0, 3] with
3 = 8·3600 s. Five different demand scenarios are generated (seeds 0–4).

Uses generate_requests_df from generate_grid_instances.py and writes
requests.csv plus a minimal config.yaml in each instance folder so the
instance loader can load them.
"""
from pathlib import Path
import sys

# Allow importing from same directory when run from project root or scripts/
_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import numpy as np
import yaml
from generate_grid_instances import generate_requests_df


# Parameters from Kronmueller et al. (2024), Section V-B, Gridworld
KRONMUELLER_2024 = {
    "size": 40,                          # n × n grid
    "requests": 1600,                    # |T|
    "max_request_start_time_s": 8 * 3600, # 3 = 8 hours in seconds
    "distance": 10,                      # b: travel time per edge (seconds)
    "n_scenarios": 5,
    "max_delay": 480                    
}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate 5 grid instances with Kronmueller et al. (2024) parameters.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_scripts_dir / "kronmueller_2024_grid_instances",
        help="Directory to write instance_0 .. instance_4 into",
    )
    parser.add_argument(
        "--seed-offset",
        type=int,
        default=0,
        help="First random seed (default 0); seeds used: offset, offset+1, ..., offset+4",
    )
    args = parser.parse_args()
    out_root = args.output_dir
    seed_offset = args.seed_offset

    n = KRONMUELLER_2024["size"]
    n_requests = KRONMUELLER_2024["requests"]
    max_request_start_time_s = KRONMUELLER_2024["max_request_start_time_s"]
    n_scenarios = KRONMUELLER_2024["n_scenarios"]
    distance = KRONMUELLER_2024["distance"]

    out_root.mkdir(parents=True, exist_ok=True)

    for i in range(n_scenarios):
        seed = seed_offset + i
        rng = np.random.default_rng(seed)
        df = generate_requests_df(n_requests, max_request_start_time_s, n, rng)

        instance_dir = out_root / f"instance_{i}"
        instance_dir.mkdir(parents=True, exist_ok=True)
        requests_path = instance_dir / "requests.csv"
        df.to_csv(requests_path, index=False)

        config = {
            "type": "grid",
            "size": n,
            "distance": distance,
            "demand": {
                "filepath": "./requests.csv",
                "min_time": 0,
                "max_time": max_request_start_time_s,
            },
            "max_travel_time_delay": {
                "mode": "absolute",
                "seconds": KRONMUELLER_2024["max_delay"]
            }
        }
        config_path = instance_dir / "config.yaml"
        with open(config_path, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"  {instance_dir}: requests.csv + config.yaml (seed={seed})")

    print(f"Done. {n_scenarios} instances in {out_root}")


if __name__ == "__main__":
    main()
