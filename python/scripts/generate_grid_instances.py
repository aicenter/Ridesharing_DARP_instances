"""
Generate grid-world DARP request instances from a YAML config.

Reads a YAML with grid size, number of requests, and time window,
samples request start times and origin/destination nodes uniformly,
and writes requests.csv in the format expected by the instance loader.
"""
from pathlib import Path
from tkinter import Y

import numpy as np
import pandas as pd
import yaml


def load_config(yaml_path: Path) -> dict:
    """Load and return the YAML config."""
    with open(yaml_path, "r") as f:
        return yaml.safe_load(f)


def generate_requests_df(
    n_requests: int,
    max_request_start_time_s: float,
    grid_size: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Create a dataframe of requests with uniformly sampled time_s, origin, and dest.

    - time_s: uniform in [0, max_request_start_time_s]
    - origin, dest: uniform in [0, grid_size^2 - 1], with origin != dest
    """
    n_nodes = grid_size * grid_size
    if n_nodes < 2:
        raise ValueError("grid size must be at least 2 so origin and destination can differ")

    time_s = rng.integers(0, max_request_start_time_s, size=n_requests)
    origins = rng.integers(0, n_nodes, size=n_requests)
    destinations = rng.integers(0, n_nodes, size=n_requests)

    # Resample dest where dest == origin
    same = origins == destinations
    while same.any():
        destinations[same] = rng.integers(0, n_nodes, size=same.sum())
        same = origins == destinations

    return pd.DataFrame({
        "time": time_s,
        "origin": origins,
        "destination": destinations,
    })


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Generate grid instance requests from YAML config.")
    parser.add_argument(
        "yaml_path",
        type=Path,
        nargs="?",
        default=Path(r"C:\Google Drive AIC\My Drive\AIC Experiment Data\Fleet-sizing\grid_world.yaml"),
        help="Path to the grid world YAML config",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()
    config_path = args.yaml_path

    config = load_config(config_path)
    n_requests = config["requests"]
    max_request_start_time_s = config["max_request_start_time_s"]
    size = config["size"]
    output_path = config_path.parent / "requests.csv"

    rng = np.random.default_rng(args.seed)
    df = generate_requests_df(n_requests, max_request_start_time_s, size, rng)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


if __name__ == "__main__":
    main()
