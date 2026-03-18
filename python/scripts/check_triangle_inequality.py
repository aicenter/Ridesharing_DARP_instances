import argparse
from pathlib import Path
import sys

import numpy as np
from tqdm import tqdm
import logging

from darpinstances.travel_time_provider import MatrixTravelTimeProvider

try:
    from numba import njit
except ImportError:
    logging.warning("Numba is not installed. Using pure Python implementation.")
    njit = None


if njit is not None:
    @njit
    def _find_violation_for_i(dm: np.ndarray, i: int):
        """
        For fixed i, scan all j, k and return the first (j, k) that violates
        d(i, k) <= d(i, j) + d(j, k), or (-1, -1) if none.
        """
        n = dm.shape[0]
        for j in range(n):
            dij = dm[i, j]
            for k in range(n):
                if dm[i, k] > dij + dm[j, k]:
                    return j, k
        return -1, -1
else:
    def _find_violation_for_i(dm: np.ndarray, i: int):
        n = dm.shape[0]
        for j in range(n):
            dij = dm[i, j]
            for k in range(n):
                if dm[i, k] > dij + dm[j, k]:
                    return j, k
        return -1, -1


def check_triangle_inequality(dm_provider: MatrixTravelTimeProvider) -> bool:
    """
    Checks whether the triangle inequality holds for all node triples in the
    provided distance matrix. Stops at the first detected violation.

    Returns True if the triangle inequality holds for all triples, False otherwise.
    """
    dm = dm_provider.dm
    if not isinstance(dm, np.ndarray):
        dm = np.asarray(dm)
    # Use an integer dtype that Numba handles efficiently
    if not np.issubdtype(dm.dtype, np.integer):
        dm = dm.astype(np.int64)

    n = dm.shape[0]

    # Outermost loop with progress indicator; inner j/k loops stay in the
    # JIT-compiled helper (or pure Python fallback if numba is unavailable).
    for i in tqdm(range(n), desc="Checking i"):
        j, k = _find_violation_for_i(dm, i)
        if j != -1:
            dij = int(dm[i, j])
            dik = int(dm[i, k])
            djk = int(dm[j, k])
            print(
                "Triangle inequality violated for nodes "
                f"i={i}, j={j}, k={k}: "
                f"d({i},{k})={dik} > d({i},{j})+d({j},{k})={dij}+{djk}"
            )
            return False

    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether a distance/travel-time matrix satisfies the triangle inequality. "
            "The matrix can be provided as a CSV or HDF file; the format is inferred from "
            "the file extension."
        )
    )
    parser.add_argument(
        "dm_path",
        type=Path,
        help="Path to the distance/travel-time matrix file (.csv or .hdf5/.h5).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dm_path: Path = args.dm_path

    if not dm_path.exists():
        print(f"Distance matrix file not found: {dm_path}")
        sys.exit(1)

    dm_provider = MatrixTravelTimeProvider.read_from_file(dm_path)

    ok = check_triangle_inequality(dm_provider)
    if ok:
        print("Triangle inequality holds for all node triples in the matrix.")
        sys.exit(0)

    sys.exit(1)


if __name__ == "__main__":
    main()

