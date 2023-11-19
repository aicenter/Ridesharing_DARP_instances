
import darpinstances.instance_generation.instance_generation

from pathlib import Path


# if len(sys.argv) < 2:
#     logging.error(" Missing path to config file. You should provide it as a first argument")

# load config
# config_filepath = sys.argv[1]
# base_filepath = r'C:\AIC Experiment Data\DARP'
# base_filepath = r'D:\Google Drive/AIC Experiment Data\DARP'
# config_filepath = f'{base_filepath}/Real Demand and speeds/NYC/experiments/final_experiments/05_min/config.yaml'
config_filepath = r'D:\Google Drive AIC/AIC Experiment Data\Ridepooling Trade-offs Article/Chicago\instances\4_am_to_4_pm/config.yaml'

darpinstances.instance_generation.instance_generation.generate_instance(Path(config_filepath))

