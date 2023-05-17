#!/usr/bin/env python3
import logging
import re
from pathlib import Path

import yaml

from darpinstances.utils import load_yaml

logging.basicConfig(level=logging.DEBUG)

if __name__ == '__main__':
    basedir = Path(r'/home/mrkosja1/darp/instances/')/"Results"
    # basedir = Path(r'/home/mrkosja1/darp/DARP-benchmark-experiments_gitlab_repo/python/darpbenchmark/test/test_data')
    # basedir = Path(r'C:\Users\mrkos\scth\projects\2023_ITSC_DARP_instances_paper\experiments\instances')
    dry_run = False

    for file_path in basedir.rglob("*config.yaml"):
        config = load_yaml(file_path)
        if "timeout" in config.keys():
            if dry_run:
                logging.info(f"Would update {file_path}")
            else:
                # pyyaml cant store comments, so we need to do it manually
                with open(file_path, "rt", encoding="utf-8") as f:
                    lines = f.readlines()

                lines = [f"#{line}" if "timeout" in line else line for line in lines]

                with open(file_path, "wt", encoding="utf-8") as f:
                    f.writelines(lines)
                logging.info(f"Updated {file_path}")



