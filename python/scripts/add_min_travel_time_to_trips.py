import logging
from pathlib import Path

import pandas as pd

from darpinstances.instance import MatrixTravelTimeProvider


def compute_trips_travel_times(dm: MatrixTravelTimeProvider, inst_path: Path):
    inst = pd.read_csv(inst_path, sep="\t")
    if "min_travel_time" not in inst.columns:
        inst["min_travel_time"] = [dm.get_travel_time(origin, destination) for origin, destination in
                                   zip(inst["origin"], inst["dest"])]
        inst.to_csv(inst_path, sep="\t", index=False)


def compute_instance_dm(dm: MatrixTravelTimeProvider, inst_path: Path):
    trips = pd.read_csv(inst_path / "trips.csv", sep="\t")
    trip_origins = trips["origin"].unique()
    trip_destinations = trips["dest"].unique()
    vehicles = pd.read_csv(inst_path / "vehicles.csv", sep="\t", names=["origin", "capacity"])
    vehicle_origins = vehicles["origin"].unique()

    locations = sorted(set(trip_origins).union(set(trip_destinations)).union(set(vehicle_origins)))
    # for location in locations:
    #     for other_location in locations:
    #         dm.get_travel_time(location, other_location)


if __name__ == '__main__':
    instances_path = Path("/home/mrkosja1/darp/instances/Instances")

    cities = [
              'NYC',
              'Manhattan',
              'Chicago',
              'DC'
    ]
    for city in cities:
        logging.info(f"Computing min travel times for city: {city}")
        city_path = instances_path / city
        dm = MatrixTravelTimeProvider.from_hdf(city_path / "dm.h5")
        for filepath in city_path.rglob("**/*trips.csv"):
            logging.info(f"Computing min travel times for instance: {filepath}")
            compute_trips_travel_times(dm, filepath)
