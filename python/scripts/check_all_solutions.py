import logging
from pathlib import Path
import os

import pandas as pd

import darpinstances.solution
import darpinstances.experiments
import darpinstances.solution_checker

# darp_path = Path(r"C:\Google Drive/AIC Experiment Data\DARP")
# darp_path = Path(r"D:\Google Drive AIC/AIC Experiment Data\DARP")
darp_path = Path(r"D:\Google Drive AIC/AIC Experiment Data\DARP")

root_paths = [
    # darp_path / Path("ITSC_instance_paper/old/Results"),

    # darp_path / "final/Results",
    darp_path / "final/Results/DC/start_18-00/duration_02_h/max_delay_03_min",
]

darpinstances.solution_checker.check_all_solutions(root_paths)