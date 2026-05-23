import logging
import math
import shutil
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd

from darpinstances.travel_time_provider import MatrixTravelTimeProvider


DEFAULT_SPEED_MPS = 14.0
BACKUP_SUFFIX = ".before_short_trip_pruning"


def _detect_csv_separator(filepath: Path) -> str:
    with open(filepath, "r", encoding="utf-8") as infile:
        first_line = infile.readline()
    if "\t" in first_line:
        return "\t"
    return ","


def _validate_bins(bins: Iterable[Dict]) -> List[Dict[str, float]]:
    validated_bins = []
    previous_threshold = None
    for bin_config in bins:
        threshold = float(bin_config["threshold"])
        ratio = float(bin_config["ratio"])
        if threshold <= 0:
            raise ValueError(f"Short-trip pruning bin threshold must be positive. Got {threshold}.")
        if ratio < 0 or ratio > 1:
            raise ValueError(f"Short-trip pruning bin ratio must be between 0 and 1. Got {ratio}.")
        if previous_threshold is not None and threshold <= previous_threshold:
            raise ValueError(
                "Short-trip pruning bins must be sorted by strictly ascending threshold. "
                f"Got {threshold} after {previous_threshold}."
            )
        validated_bins.append({"threshold": threshold, "ratio": ratio})
        previous_threshold = threshold
    if not validated_bins:
        raise ValueError("short_trips_pruning.bins must contain at least one bin.")
    return validated_bins


def _get_speed_mps(config: Dict) -> float:
    if config.get("speed_mps") is not None:
        speed_mps = float(config["speed_mps"])
    elif config.get("speed_kmh") is not None:
        speed_mps = float(config["speed_kmh"]) / 3.6
    else:
        speed_mps = DEFAULT_SPEED_MPS
    if speed_mps <= 0:
        raise ValueError(f"short_trips_pruning speed must be positive. Got {speed_mps}.")
    return speed_mps


def _get_destination_column(requests: pd.DataFrame) -> str:
    if "dest" in requests.columns:
        return "dest"
    if "destination" in requests.columns:
        return "destination"
    raise ValueError("Requests file must contain a dest or destination column.")


def _compute_trip_distances_m(
    requests: pd.DataFrame,
    dm: MatrixTravelTimeProvider,
    speed_mps: float,
) -> np.ndarray:
    if "origin" not in requests.columns:
        raise ValueError("Requests file must contain an origin column.")
    destination_column = _get_destination_column(requests)
    travel_times = np.array(
        [
            dm.get_travel_time(int(origin), int(destination))
            for origin, destination in zip(requests["origin"], requests[destination_column])
        ],
        dtype=float,
    )
    return travel_times * speed_mps


def _select_discarded_indices(
    distances_m: np.ndarray,
    bins: List[Dict[str, float]],
    seed: int,
) -> set:
    rng = np.random.default_rng(seed)
    discarded_indices = set()
    previous_threshold = 0.0

    for bin_index, bin_config in enumerate(bins):
        threshold = bin_config["threshold"]
        ratio = bin_config["ratio"]
        if bin_index == 0:
            bin_mask = (distances_m >= previous_threshold) & (distances_m <= threshold)
        else:
            bin_mask = (distances_m > previous_threshold) & (distances_m <= threshold)
        candidate_indices = np.flatnonzero(bin_mask)
        discard_count = math.floor(len(candidate_indices) * ratio)
        if discard_count > 0:
            discarded = rng.choice(candidate_indices, size=discard_count, replace=False)
            discarded_indices.update(int(index) for index in discarded)
        logging.info(
            "Short-trip pruning bin (%s, %s] m: %s candidates, ratio %.4f, discarded %s.",
            previous_threshold,
            threshold,
            len(candidate_indices),
            ratio,
            discard_count,
        )
        previous_threshold = threshold

    return discarded_indices


def prune_short_trips(config: Dict) -> pd.DataFrame:
    requests_filepath = Path(config["requests_filepath"])
    dm_filepath = Path(config["dm_filepath"])
    backup_filepath = requests_filepath.with_name(requests_filepath.name + BACKUP_SUFFIX)

    if not requests_filepath.exists():
        raise FileNotFoundError(f"Requests file not found: {requests_filepath}")
    if not dm_filepath.exists():
        raise FileNotFoundError(f"Distance matrix file not found: {dm_filepath}")
    if backup_filepath.exists():
        raise FileExistsError(
            f"Short-trip pruning backup already exists: {backup_filepath}. "
            "Remove it manually before pruning this requests file again."
        )

    bins = _validate_bins(config["bins"])
    speed_mps = _get_speed_mps(config)
    seed = int(config.get("seed", 0))

    separator = _detect_csv_separator(requests_filepath)
    requests = pd.read_csv(requests_filepath, sep=separator)
    original_count = len(requests)
    logging.info(
        "Short-trip pruning loaded %s requests from %s.",
        original_count,
        requests_filepath,
    )

    dm = MatrixTravelTimeProvider.read_from_file(dm_filepath)
    distances_m = _compute_trip_distances_m(requests, dm, speed_mps)
    discarded_indices = _select_discarded_indices(distances_m, bins, seed)

    pruned_requests = requests.drop(index=sorted(discarded_indices))

    shutil.copy2(requests_filepath, backup_filepath)
    logging.info("Backed up original requests to %s.", backup_filepath)

    pruned_requests.to_csv(requests_filepath, sep=separator, index=False)
    logging.info(
        "Short-trip pruning wrote %s requests to %s (%s discarded).",
        len(pruned_requests),
        requests_filepath,
        original_count - len(pruned_requests),
    )

    return pruned_requests
