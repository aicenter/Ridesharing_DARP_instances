import logging
from pathlib import Path
import os

import pandas as pd

import darpinstances.solution
import darpinstances.experiments
import darpinstances.solution_checker

# darp_path = Path(r"C:\Google Drive/AIC Experiment Data\DARP")
darp_path = Path(r"D:\Google Drive AIC/AIC Experiment Data\DARP")

root_paths = [
    # darp_path / Path("Results/final-real_speeds/NYC-increased_start_time"),
    # darp_path / Path("Results/final-real_speeds/Manhattan"),
    # darp_path / Path("Results/final-real_speeds/Chicago-increased_start_time"),
    # darp_path / Path("Results/final-real_speeds/DC-more_vehicles")
    # darp_path / Path("ITSC_instance_paper/old/Results"),

    darp_path / "final/Results",
]

logging.info('Checking solutions in the following root paths: \n%s', '\n'.join((str(path) for path in root_paths)))




# dirs = pd.DataFrame(names=["root", 'files'])
dirs = []

for root_path in root_paths:
    for root, dir, files in os.walk(root_path):
        for file in files:
            filename = os.fsdecode(file)
            if filename == "config.yaml-solution.json":
                filepath = os.path.join(root, filename)
                dirs.append((root, filepath))
                break

dir_df = pd.DataFrame(dirs, columns=["root", "solution path"])
logging.info("%d solutions found", len(dir_df))

# sort by area
dir_df['area'] = dir_df['root'].apply(lambda path: Path(path).parts[-5])
dir_df.sort_values(by=['area'], inplace=True)

stats = {}
last_instance_path = None
last_instance = None
travel_time_provider = None
last_area = None
for root, solution_path, area in zip(dir_df['root'], dir_df['solution path'], dir_df['area']):
    config_path = os.path.join(root, "config.yaml")
    experiment_config = darpinstances.experiments.load_experiment_config(config_path)
    instance_path = Path(experiment_config['instance'])
    if instance_path == last_instance_path:
        instance = last_instance
    else:
        if last_area == area:
            instance, _ = darpinstances.solution_checker.load_instance(instance_path, last_instance.travel_time_provider)
        else:
            instance, _ = darpinstances.solution_checker.load_instance(instance_path)

    solution = darpinstances.solution.load_solution(solution_path, instance)
    if solution.feasible:
        stats[solution_path] = darpinstances.solution_checker.check_solution(instance, solution)

    last_instance_path = instance_path
    last_instance = instance
    last_area = area

stat_df = pd.DataFrame(stats.items())
stat_df.columns = ['solution path', 'ok']

logging.info("Checked %d solutions", len(stats))
pd.set_option('display.max_colwidth', None)
pd.set_option('display.max_rows', None)
logging.info("Stats: \n%s", stat_df)

stats_er = stat_df[stat_df['ok'] == False]
if len(stats_er) > 0:
    logging.error("Found %d errors", len(stats_er))
    logging.error("Error solutions: \n%s", stats_er)