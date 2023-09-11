import os
from pathlib import Path

import darpinstances.log
import darpinstances.instance_generation.instance_generation

"""
This script generates all DARP instances based on configurations in directory. The map and dm files are created only
once if they does not exist.
"""

# root_path = r'D:\AIC Data/Experiment Data\DARP\Manhattan\experiments/max_delay-exp_length_SA_min_vehicles'
# root_path = r'C:\Google Drive/AIC Experiment Data\DARP\Real Demand and speeds/Chicago/experiments/final_experiments-more_vehicles'
# root_path = r'C:\AIC Experiment Data\DARP\Real Demand and speeds/Chicago'

root_path = r'C:\Google Drive\AIC Experiment Data\DARP\ITSC_instance_paper\Instances\Chicago\instances\start_07-00'


for root, dir, files in os.walk(root_path):
    for file in files:
        filename = os.fsdecode(file)
        if filename == "config.yaml":
            filepath = Path(root) / filename
            darpinstances.instance_generation.instance_generation.generate_instance(filepath)