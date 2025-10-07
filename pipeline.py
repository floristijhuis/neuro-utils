#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
===================================================================================================
                        PIPELINE COORDINATION SCRIPT FOR NEUROIMAGING
===================================================================================================
Running this script coordinates modules for processing (neuroimaging) data, both preprocessing, processing, postprocessing.
Each module is a separate script located in the "scripts" folder. The modules can be run sequentially or independently.
The script uses argparse to handle command-line arguments, allowing users to specify the project name, modules to run,
and optional subject/session/run filters.

It assumes the presence of a project-specific directory with yaml that contains settings and descriptions of the dataset.
This project-specific directory should be located in ~/projects/<project_name>. Within this project folder, the master
script looks for a "configs" folder with a "dataset.yml" file that contains the dataset description and settings.
These settings contain the project name, BIDS directory, derivatives directory, scratch directory, subjects, sessions, and runs in the dataset,
number of CPUs, memory in GB, and other relevant settings.

During each step, the pipeline copies all necessary files from the mounted project folder to a processing folder on the fast local scratch disk.
After processing, the outputs are copied back to the project folder in a "derivatives" folder.

When you run the pipeline, make sure to use nohup, so that it keeps running when you log out:
nohup python -u pipeline.py -p <project_name> -m <modules> & disown

Modules that can be used:
01: mriqc - MRIQC preprocessing module for a BIDS dataset.
02: fmriprep - fMRIPrep preprocessing module for a BIDS dataset.

===================================================================================================
"""

__author__ = "Floris Tijhuis"
__contact__ = "f.b.tijhuis@uva.nl"
__date__ = "2025/10/06"   ### Date it was created
__status__ = "Production" ### Production = still being developed. Else: Concluded/Finished.

####################
# Review History   #
####################

# Reviewed by Name Date ### 

####################
# Libraries        #
####################

# Standard imports  ### (Put here built-in libraries - https://docs.python.org/3/library/)
import argparse
import subprocess
import sys
import contextlib
import os
from datetime import datetime
from pathlib import Path

# Custom imports ### (Put here custom libraries)
from utils.utils import log_summary, load_yaml

# --------------------------
# Config
# --------------------------
PROJECTS_DIR = Path(os.path.expanduser("~/projects"))

MODULE_DICT = {"01": "mriqc", 
               "02": "fmriprep"}

# Define summary csv
SUMMARY_CSV = PROJECTS_DIR / "pipeline_summary.csv"

# --------------------------
# Helper function to run single module
# --------------------------

def run_module(project, module_name, project_yaml, project_logs_dir, subjects=None, sessions=None, runs=None, extra_args=None):
    """Run a module using a nohup process with nohup and logging."""
    # First, load config for settings
    config = load_yaml(project_yaml)

    subjects = subjects if subjects is not None else config.get("subjects", [])
    sessions = sessions if sessions is not None else config.get("sessions", [])
    runs = runs if runs is not None else config.get("runs", [])
    extra_args = extra_args or []

    # Create log file
    log_file = project_logs_dir/ f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{module_name}.log"

    # Build command
    cmd = ["nohup", "python", "-u", "-m", f"scripts.{module_name}"]  # assumes module_script is a python module in scripts/. maybe nohup should be removed as the pipeline itself is also called with nohup
    cmd += ["-c"] + [str(project_yaml)]
    cmd += ["-s"] + subjects
    cmd += ["-n"] + sessions
    cmd += ["-r"] + runs
    cmd += extra_args

    print(f"Running module: {' '.join(cmd)}")
    print(f"Logging to {log_file} \n")
    print(f"Success status will be logged to {SUMMARY_CSV}")

    with open(log_file, "w") as f, contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
        try:
            print(f"Running module {module_name} with command: {' '.join(cmd)} \n", flush=True)
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True, text=True)
            log_summary(SUMMARY_CSV, project, subjects, sessions, runs, module_name, True)
            print(f"[SUCCESS] Module {module_name} finished for subjects {subjects}")
        except subprocess.CalledProcessError as e:
            log_summary(SUMMARY_CSV, project, subjects, sessions, runs, module_name, False, str(e))
            print(f"[ERROR] Module {module_name} failed for subjects {subjects}")
            raise
    return True

# --------------------------
# Main CLI for pipeline
# --------------------------
def main():

    parser = argparse.ArgumentParser(description="Master pipeline script for neuroimaging data processing. See script header for details.")
    parser.add_argument("-p", "--project", required=True, help="Project name")
    parser.add_argument("-m", "--modules", nargs="+", required=True, help="Space-separated list of modules to run")
    parser.add_argument("-s", "--subject", nargs="+", help="Space-separated list of subject IDs (optional)")
    parser.add_argument("-n", "--session", nargs="+", help="Space-separated list of session numbers (optional)")
    parser.add_argument("-r", "--run", nargs="+", help="Space-separated list of run numbers (optional)")
    parser.add_argument("-x", "--extra_args", nargs="*", help="Extra args for module scripts") # I'm not doing anything with this at the moment, but might become relevant in the future
    args = parser.parse_args()

    # Load configs and set paths
    project_path = PROJECTS_DIR / args.project
    project_yaml = project_path / "configs" / "dataset.yaml"

    # Creating project-specific log dir
    project_logs_dir = project_path / "logs"
    print("Creating project-specific log dir if it does not exist already:", project_logs_dir)
    project_logs_dir.mkdir(exist_ok=True)

    # Use space-separated lists for subjects/sessions/runs
    subjects = args.subject if args.subject else None
    sessions = args.session if args.session else None
    runs = args.run if args.run else None

    # Load processing modules
    modules = args.modules

    # Loop over modules and run them
    print("Starting pipeline at: ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "\n")
    print("-" * 50)
    for module in modules:
        module_name = MODULE_DICT.get(module.strip())
        if not module_name:
            print(f"Unknown module: {module}. Skipping. \n")
            continue
        else:
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f": Running module: {module_name}")
            try:
                run_module(args.project, module_name, project_yaml, project_logs_dir, subjects, sessions, runs, args.extra_args)
                print(f"Finished module {module_name} at: ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                print("-" * 50, '\n')
            except Exception as e:
                print(f"[ERROR] Module {module_name} failed with error: {e}")
                print("Exiting pipeline.")
                print("-" * 50, '\n')
                sys.exit(1)

    print("Pipeline finished at: ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

if __name__ == "__main__":
    main()