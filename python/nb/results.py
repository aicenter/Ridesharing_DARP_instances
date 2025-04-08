from pathlib import Path
from darpinstances.results import load_occupancies_in_dir
import pandas as pd

# /home/dominika/Desktop/deathOFbachelor/final-results/1-run-23-3

RESULTS_PATH = Path('/home/dominika/Desktop/deathOFbachelor/final-results/1-run-23-3/Results')
areas = ['Porto', 'Sydney', 'DC', 'Manhattan', 'Chicago', 'NYC']

oc_df = pd.DataFrame()
for area in areas:
    res_in_area = load_occupancies_in_dir(RESULTS_PATH / area)
    if res_in_area is None:
        continue
    res_in_area['area'] = area
    oc_df = pd.concat([oc_df, res_in_area], ignore_index=True)
    # os.chdir(PATH)