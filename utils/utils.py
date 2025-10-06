#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This file contains helper functions used across the preprocessing and analysis pipelines.
"""

__author__ = "Floris Tijhuis"
__contact__ = "f.b.tijhuis@uva.nl"
__date__ = "2025/10/03"   ### Date it was created
__status__ = "Production" ### Production = still being developed. Else: Concluded/Finished.

####################
# Review History   #
####################

# Reviewed by Name Date ### 

####################
# Libraries        #
####################

# Standard imports  ### (Put here built-in libraries - https://docs.python.org/3/library/)
import csv
import shutil
import yaml
import sys
from pathlib import Path
from datetime import datetime

def remove_work_dir(work_dir: str):
    """Removes work directory if it exists."""
    work_dir = Path(work_dir)
    if work_dir.exists() and work_dir.is_dir():
        try:
            shutil.rmtree(work_dir)
            print(f"Successfully removed work directory: {work_dir}")
        except Exception as e:
            print(f"Error removing work directory {work_dir}: {e}")
    else:
        print(f"Work directory {work_dir} does not exist or is not a directory.")

def copytree_gvfs(src, dst):
    """Copies directory in a way that does not crash when copying from Tux17 to mounted FMG drive."""
    src = Path(src)
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        dest_item = dst / item.name
        if item.is_dir():
            copytree_gvfs(item, dest_item)
        else:
            shutil.copyfile(item, dest_item)

def move_outputs(temp_output_dir: str, final_output_dir: str, overwrite: bool = True):
    """Moves outputs from temp directory to final output directory, handling cross-filesystem moves.
    Removes temp directory if empty after move."""
    temp_output_dir = Path(temp_output_dir)
    final_output_dir = Path(final_output_dir)

    if not temp_output_dir.exists():
        raise FileNotFoundError(f"Temp dir {temp_output_dir} does not exist")

    final_output_dir.mkdir(parents=True, exist_ok=True)

    for item in temp_output_dir.iterdir():
        dest = final_output_dir / item.name

        if dest.exists():
            if overwrite:
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
                print(f"Overwriting {dest}")
            else:
                print(f"Skipping existing {dest}")
                continue

        try:
            # Try a normal move (fast if on same filesystem)
            shutil.move(str(item), str(dest))
        except OSError as e:
            print(f"Cannot move directly. Copying {item} instead...")
            if item.is_dir():
                copytree_gvfs(item, dest)
                shutil.rmtree(item)
            else:
                shutil.copyfile(item, dest)
                item.unlink()

    # Try cleaning up temp dir if empty
    try:
        temp_output_dir.rmdir()
        print(f"Removed empty temp dir {temp_output_dir}")
    except OSError:
        print(f"Temp dir {temp_output_dir} not empty, manual cleanup may be needed")

def log_summary(logfile, project, subject, session, run, module, success, errmsg=""):
    """Append a summary entry to the CSV log.
    If subject/session/run are lists, join their entries with spaces."""
    logfile = Path(logfile)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    write_header = not logfile.exists()

    def join_if_list(val):
        if isinstance(val, list):
            return " ".join(str(x) for x in val)
        return str(val)

    with open(logfile, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "project", "subject", "session", "run", "module", "success", "error"])
        writer.writerow([
            datetime.now(),
            project,
            join_if_list(subject),
            join_if_list(session),
            join_if_list(run),
            module,
            success,
            errmsg
        ])

def load_yaml(yaml_path: str):
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Config file {yaml_path} not found.")
    print(f"Using config file: {yaml_path}", flush=True)

    # Load YAML
    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    return config
