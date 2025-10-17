#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MRIQC group processing module for a BIDS dataset.
This module runs MRIqc for the entire derivatives/mriqc/ folder. It requires participant-level to have been run previously.
Usually called from pipeline.py in the main neuro-utils repo, but can also be run directly from the terminal:
    nohup python -u -m scripts.mriqc_group
Calls the mriqc_group_wrapper.sh script in neuro-utils/bin, which is necessary for setting up Docker environment for running MRIqc.
Subject/Session/Run flags are ignored in this script, as it is a group-level analysis.
The script first copies the mriqc output into the scratch directory, after which the group-level analysis is added.
"""

__author__ = "Floris Tijhuis"
__contact__ = "f.b.tijhuis@uva.nl"
__date__ = "2025/10/09"   ### Date it was created
__status__ = "Production" ### Production = still being developed. Else: Concluded/Finished.

####################
# Review History   #
####################

# Reviewed by Name Date ### 

####################
# Libraries        #
####################

# Standard imports  ### (Put here built-in libraries - https://docs.python.org/3/library/)
import subprocess
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Third-party imports  ### (Put here third-party libraries - https://pypi.org/)
import git

# Custom imports ### (Put here custom libraries)
from utils.utils import remove_dir, load_yaml, copytree_gvfs
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

def main():
    # --------------------------
    # Argument parsing
    # --------------------------
    parser = argparse.ArgumentParser(
        description="Run MRIqc group-level processing on MRIqc outputs."
    )

    # Standard arguments
    parser.add_argument("-c", "--config", required=True, help="Path to project YAML config file")
    parser.add_argument("-s", "--subjects", nargs="+", help="Space-separated list of subject IDs (optional)")
    parser.add_argument("-n", "--sessions", nargs="+", help="Space-separated list of session numbers (optional)")
    parser.add_argument("-r", "--runs", nargs="+", help="Space-separated list of run numbers (optional)")

    args = parser.parse_args()

    # --------------------------
    # Start timer
    # --------------------------
    start_time = datetime.now()
    log.info("MRIqc groups module started")

    # --------------------------
    # Load configuration
    # --------------------------
    # Load configuration file
    config = load_yaml(Path(args.config))

    # Extract settings from config file
    bids_dir = Path(config.get("bids_dir"))
    if not bids_dir.exists():
        raise FileNotFoundError(f"BIDS directory does not exist: {bids_dir}")
    
    derivatives_dir = Path(config.get("derivatives_dir"))
    scratch_dir = Path(config.get("scratch_dir"))
    n_cpus = config.get("n_cpus")
    mem_gb = config.get("mem_gb")

    # --------------------------
    # Prepare paths
    # --------------------------
    # Define the paths
    repo_root = Path(git.Repo(Path(__file__), search_parent_directories=True).working_tree_dir)
    neuro_utils_bin = repo_root / "bin"
    scratch_dir_mriqc = scratch_dir / "MemoryLane" / "mriqc"
    temp_bids_dir = scratch_dir_mriqc / "bids"
    work_dir_mriqc = scratch_dir_mriqc / "work"
    temp_output_dir_mriqc = scratch_dir_mriqc / "output"
    final_output_dir_mriqc = derivatives_dir / "mriqc"

    # Check if final_output_dir_exist; otherwise throw an error
    if not final_output_dir_mriqc.exists():
        raise FileNotFoundError(f"Participant-level mriqc output not found in {final_output_dir_mriqc}, exiting script...")
    
    # Create the scratch directories if they do not exist
    temp_bids_dir.mkdir(parents=True, exist_ok=True)
    work_dir_mriqc.mkdir(parents=True, exist_ok=True)
    temp_output_dir_mriqc.mkdir(parents=True, exist_ok=True)

    # Copy the BIDS directory to scratch
    log.info("Copying BIDS directory to scratch...")
    copytree_gvfs(bids_dir, temp_bids_dir, silent=True)
    # Copy pre-existing MRIqc output to scratch
    log.info("Copying MRIqc output directory to scratch...")
    copytree_gvfs(final_output_dir_mriqc, temp_output_dir_mriqc, silent=True)

    cmd = [
    "bash",
    str(neuro_utils_bin / "mriqc_group_wrapper.sh"),
    str(temp_bids_dir),
    str(temp_output_dir_mriqc),
    str(work_dir_mriqc),
    ]

    # Add numeric parameters
    cmd += [str(n_cpus), str(mem_gb)]

    # --------------------------
    # Run MRIQC
    # --------------------------
    log.info(f"Running MRIqc group-level wrapper with command {' '.join(cmd)} \n")
    subprocess.run(cmd, check=True)

    # --------------------------
    # Postprocessing: move + cleanup
    # --------------------------
    final_output_dir_mriqc = derivatives_dir / "mriqc"
    log.info(f"Moving outputs from {temp_output_dir_mriqc} → {final_output_dir_mriqc}; overwriting original MRIqc output")
    copytree_gvfs(temp_output_dir_mriqc, final_output_dir_mriqc, remove_src=True)

    log.info(f"Removing work directory {scratch_dir_mriqc} to save space...")
    remove_dir(scratch_dir_mriqc)

    log.info("MRIqc group-level processing complete. \n")
    log.info(f"Final outputs located at: {final_output_dir_mriqc}")

    # --------------------------
    # End timer
    # --------------------------
    end_time = datetime.now()
    elapsed = end_time - start_time
    log.info(f"Elapsed time: {elapsed}")

if __name__ == "__main__":
    main()