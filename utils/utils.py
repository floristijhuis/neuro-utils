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
from pathlib import Path
from datetime import datetime

def remove_dir(dir_path: str):
    """Removes directory if it exists."""
    dir_path = Path(dir_path)
    if dir_path.exists() and dir_path.is_dir():
        try:
            shutil.rmtree(dir_path)
            print(f"Successfully removed directory: {dir_path}")
        except Exception as e:
            print(f"Error removing directory {dir_path}: {e}")
    else:
        print(f"Directory {dir_path} does not exist or is not a directory.")

def copytree_gvfs(src, dst, remove_src=False):
    """Copies directory in a way that does not crash when copying from Tux17 to mounted FMG drive or inverse. If remove_src 
    is True, source files are removed after copying."""
    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        raise FileNotFoundError(f"Source dir {src} does not exist")
    
    dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        dest_item = dst / item.name
        if item.is_dir():
            copytree_gvfs(item, dest_item, remove_src)
        else:
            print("Copying/Moving file:", item, "→", dest_item)
            shutil.copyfile(item, dest_item)
            if remove_src:
                item.unlink()

    if remove_src:
        try:
            print("Removing source directory:", src)
            src.rmdir()
        except OSError as e:
            print(f"Could not remove source directory {src} (it might not be empty): {e}")

def log_summary(logfile, project, subject, session, run, module, success, errmsg=""):
    """Append a summary entry to the CSV log. If subject/session/run are lists, join their entries with spaces."""
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
    """Loads a YAML file and returns its contents as a dictionary."""
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Config file {yaml_path} not found.")
    print(f"Using config file: {yaml_path}", flush=True)

    # Load YAML
    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    return config
