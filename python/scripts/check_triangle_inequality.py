import argparse
from pathlib import Path
import sys

from darpinstances.travel_time_provider import MatrixTravelTimeProvider


def check_triangle_inequality(dm_provider: MatrixTravelTimeProvider) -> bool:
    """
    Checks whether the triangle inequality holds for all node triples in the
    provided distance matrix. Stops at the first detected violation.

    Returns True if the triangle inequality holds for all triples, False otherwise.
    """
    n = dm_provider.get_node_count()

    for i in range(n):
        for j in range(n):
            dij = dm_provider.get_travel_time(i, j)
            for k in range(n):
                dik = dm_provider.get_travel_time(i, k)
                djk = dm_provider.get_travel_time(j, k)

                if dik > dij + djk:
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

