# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%
from pathlib import Path
import json

import plotly.express as px


SOLUTION_PATH = Path(r"C:/Google Drive AIC/My Drive/AIC Experiment Data/DARP/Results/IH_benchmark/v1/length_32/output/config.yaml-solution.json")

with SOLUTION_PATH.open("r", encoding="utf-8") as solution_file:
    solution = json.load(solution_file)

plan_lengths = [len(plan.get("actions", [])) for plan in solution.get("plans", [])]

fig = px.histogram(
    x=plan_lengths,
    nbins=max(1, min(50, len(set(plan_lengths)) or 1)),
    labels={"x": "Plan length (actions)", "y": "Number of plans"},
    title=f"Plan length distribution ({SOLUTION_PATH.name})",
)
fig.update_layout(bargap=0.05)

if plan_lengths and max(plan_lengths) <= 50:
    fig.update_xaxes(dtick=1)

fig.show()

