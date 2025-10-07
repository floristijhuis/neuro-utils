#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MRIQC processing module for a BIDS dataset.
Usually called from pipeline.py in the main neuro-utils repo, but can also be run directly from the terminal:
    nohup python -u -m scripts.mriqc -s P005 P010 ... -n 1 2 -r 1 2 &
Calls the mriqc_wrapper.sh script in neuro-utils/bin, which is necessary for setting up Docker environment for running MRIqc.

N.B. 'Run' flag will be removed from newer versions of MRIqc, so be careful with this.
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

# Third-party imports  ### (Put here third-party libraries - https://pypi.org/)
import git

# Custom imports ### (Put here custom libraries)
from utils.utils import move_outputs, remove_work_dir, load_yaml, copytree_gvfs

def main():
    # --------------------------
    # Argument parsing
    # --------------------------
    parser = argparse.ArgumentParser(
        description="Run MRIqc preprocessing on BIDS dataset."
    )
    parser.add_argument("-c", "--config", required=True, help="Path to project YAML config file")
    parser.add_argument("-s", "--subjects", nargs="+", help="Space-separated list of subject IDs (optional)")
    parser.add_argument("-n", "--sessions", nargs="+", help="Space-separated list of session numbers (optional)")
    parser.add_argument("-r", "--runs", nargs="+", help="Space-separated list of run numbers (optional)")
    args = parser.parse_args()

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

    # Create the directories if they do not exist
    temp_bids_dir.mkdir(parents=True, exist_ok=True)
    work_dir_mriqc.mkdir(parents=True, exist_ok=True)
    temp_output_dir_mriqc.mkdir(parents=True, exist_ok=True)

    # Move the BIDS directory to scratch
    print("Copying BIDS directory to scratch...")
    copytree_gvfs(bids_dir, temp_bids_dir) # This may need to be changed, as it copies the entire BIDS folder, which is not necessary if you run on specific subjects only.
    
    cmd = [
    "bash",
    str(neuro_utils_bin / "mriqc_wrapper.sh"),
    str(temp_bids_dir),
    str(temp_output_dir_mriqc),
    str(work_dir_mriqc),
    ]

    # Add space-separated lists (if any)
    # Add joined string arguments (each becomes one argument)
    if args.subjects:
        cmd.append(" ".join(args.subjects))
    else:
        cmd.append("")

    if args.sessions:
        cmd.append(" ".join(args.sessions))
    else:
        cmd.append("")

    if args.runs:
        cmd.append(" ".join(args.runs))
    else:
        cmd.append("")

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
    move_outputs(temp_output_dir_mriqc, final_output_dir_mriqc, overwrite=True)

    print(f"Removing work directory {work_dir_mriqc} to save space...")
    remove_work_dir(work_dir_mriqc)
    remove_work_dir(scratch_dir_mriqc)

    print("MRIqc processing complete. \n")
    print(f"Final outputs located at: {final_output_dir_mriqc}")

if __name__ == "__main__":
    main()