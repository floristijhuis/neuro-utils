#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MRIQC processing module for a BIDS dataset.
Usually called from pipeline.py in the main neuro-utils repo, but can also be run directly from the terminal:
    nohup python -u -m scripts.mriqc -s P005 P010 ... -n 1 2 -r 1 2 &
Calls the mriqc_wrapper.sh script in neuro-utils/bin, which is necessary for setting up Docker environment for running MRIqc.
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
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# Third-party imports  ### (Put here third-party libraries - https://pypi.org/)
import git

# Custom imports ### (Put here custom libraries)
from utils.utils import remove_dir, load_yaml, copytree_gvfs, update_bids_filter_file_entry
import json
from pathlib import Path

def main():
    # --------------------------
    # Argument parsing
    # --------------------------
    parser = argparse.ArgumentParser(
        description="Run MRIqc preprocessing on BIDS dataset."
    )

    # Standard arguments
    parser.add_argument("-c", "--config", required=True, help="Path to project YAML config file")
    parser.add_argument("-s", "--subjects", nargs="+", help="Space-separated list of subject IDs (optional)")
    parser.add_argument("-n", "--sessions", nargs="+", help="Space-separated list of session numbers (optional)")
    parser.add_argument("-r", "--runs", nargs="+", help="Space-separated list of run numbers (optional)")

    # Specific MRIqc arguments
    parser.add_argument(
        "--anat_only",
        action="store_true",
        help="Run MRIQC on anatomical data only (default: run all types)"
    )

    parser.add_argument(
        "--func_only",
        action="store_true",
        help="Run MRIQC on functional data only (default: run all types)"
    )

    args = parser.parse_args()

    # --------------------------
    # Start timer
    # --------------------------
    start_time = datetime.now()
    print(f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] MRIqc module started")

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
    filter_file = config.get("bids_filter_file")

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

    # Create the directories if they do not exist
    temp_bids_dir.mkdir(parents=True, exist_ok=True)
    work_dir_mriqc.mkdir(parents=True, exist_ok=True)
    temp_output_dir_mriqc.mkdir(parents=True, exist_ok=True)

    # Copy the BIDS directory to scratch
    print("Copying BIDS directory to scratch...")
    copytree_gvfs(bids_dir, temp_bids_dir, silent=True) # This may need to be changed, as it copies the entire BIDS folder, which is not necessary if you run on specific subjects only.
    
    # Modulate BIDS filter file based on your input arguments for subjects, sessions, runs, and anat/func only
    print("Generating BIDS filter file based on your inputs...")
    with Path(filter_file).open("r") as fh:
        bids_filter = json.load(fh)

    # Only modulate when all three lists are provided (as requested)
    for main_sequence_type in bids_filter.keys():
        if args.subjects:
            update_bids_filter_file_entry(bids_filter[main_sequence_type], "subject", args.subjects)
        if args.sessions:
            update_bids_filter_file_entry(bids_filter[main_sequence_type], "session", args.sessions)
        if args.runs:
            update_bids_filter_file_entry(bids_filter[main_sequence_type], "run", args.runs)
        
        if args.anat_only and main_sequence_type != "t1w":
            bids_filter[main_sequence_type]["subject"] = None

        if args.func_only and main_sequence_type != "bold":
            bids_filter[main_sequence_type]["subject"] = None


    tmp_filter_path = temp_bids_dir / "bids_filter_file.json"

    with tmp_filter_path.open("w") as fh:
        json.dump(bids_filter, fh, indent=2)

    cmd = [
    "bash",
    str(neuro_utils_bin / "mriqc_wrapper.sh"),
    str(temp_bids_dir),
    str(temp_output_dir_mriqc),
    str(work_dir_mriqc),
    ]

    # Add numeric parameters
    cmd += [str(n_cpus), str(mem_gb)]

    # --------------------------
    # Run MRIQC
    # --------------------------
    print(f"Running MRIqc wrapper with command {' '.join(cmd)} \n")
    subprocess.run(cmd, check=True)

    # --------------------------
    # Postprocessing: move + cleanup
    # --------------------------
    final_output_dir_mriqc = derivatives_dir / "mriqc"
    print(f"Moving outputs from {temp_output_dir_mriqc} → {final_output_dir_mriqc}")
    copytree_gvfs(temp_output_dir_mriqc, final_output_dir_mriqc, remove_src=True)

    print(f"Removing work directory {scratch_dir_mriqc} to save space...")
    remove_dir(scratch_dir_mriqc)

    print("MRIqc processing complete. \n")
    print(f"Final outputs located at: {final_output_dir_mriqc}")

    # --------------------------
    # End timer
    # --------------------------
    end_time = datetime.now()
    elapsed = end_time - start_time
    print(f"[{end_time.strftime('%Y-%m-%d %H:%M:%S')}] MRIqc module finished")
    print(f"Elapsed time: {elapsed}")

if __name__ == "__main__":
    main()