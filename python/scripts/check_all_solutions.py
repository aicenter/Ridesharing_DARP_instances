import logging
from pathlib import Path
import os

import pandas as pd

import darpinstances.solution
import darpinstances.experiments
import darpinstances.solution_checker
from darpinstances.solution_checker import SolutionChecker

# darp_path = Path(r"C:\Google Drive/AIC Experiment Data\DARP")
# darp_path = Path(r"D:\Google Drive AIC/AIC Experiment Data\DARP")
darp_path = Path(r"D:\Google Drive AIC/AIC Experiment Data\DARP")
fleet_sizing_path = Path(r"C:\Google Drive AIC/My Drive/AIC Experiment Data/Fleet-sizing")

root_paths = [
    # darp_path / Path("ITSC_instance_paper/old/Results"),

    # darp_path / "final/Results",
    # darp_path / "final/Results/DC/start_18-00/duration_02_h/max_delay_03_min",
    fleet_sizing_path / "kronmueller_2024_grid_instances/",
]

checker = SolutionChecker(max_error_count=10)
checker.check_all_solutions(root_paths, area_index_in_path=None, fleet_sizing=True)