from pathlib import Path
from darpinstances.instance import load_instance_config
from darpinstances.instance_generation.instance_generation import generate_instance
from roadgraphtool import db
from roadgraphtool.config import parse_config_file

config_db = Path('/home/dominika/Desktop/smart-mobility/road-graph-tool/config.yml')
config_instance = Path('/home/dominika/Desktop/deathOFbachelor/new_instances/Instances/Porto/instances/config.yaml')
# config_filepath = Path('/home/dominika/Desktop/deathOFbachelor/new_instances/Instances/Sydney/instances/config.yaml')

config = parse_config_file(config_db)
db.init_db(config)
generate_instance(config_instance)