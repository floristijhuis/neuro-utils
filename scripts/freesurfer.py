#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Running Freesurfer on anatomical scans to perform surface reconstructions.
Usually called from pipeline.py in the main neuro-utils repo, but can also be run directly from the terminal:
    nohup python -u -m scripts.freesurfer -s P005 P010 ... -n 1 2 -r 1 2 &
Some of the input arguments are ignored; 'runs' and 'sessions' are not taken into account.

The script tries to parallellize efficiently based on the maximum capacity of the server and the number of subjects you want to run.
The optimal settings were taken from https://rcs.bu.edu/examples/imaging/freesurfer/reconall/#running-recon-all-on-the-scc, and
https://surfer.nmr.mgh.harvard.edu/fswiki/SystemRequirements.
It is suggested that 4Gb is required per subject, and that optimal performance occurs at maximum 8 cores per subject.
This function assumes that Freesurfer is installed and available from the terminal when calling recon-all (try this yourself first).
"""

__author__ = "Floris Tijhuis"
__contact__ = "f.b.tijhuis@uva.nl"
__date__ = "2025/10/10"   ### Date it was created
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
import shutil
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Custom imports ### (Put here custom libraries)
from utils.utils import remove_dir, load_yaml, copytree_gvfs

# --------------------------
# Setup logging (thread-safe)
# --------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

def run_recon_all(subject, input_scan, output_dir, n_threads_max, hemi_in_parallel):
    """Run recon_all for a specific subject"""

    cmd = [
    "recon-all",
    "-all",
    "-subjid", f"sub-{subject}",
    "-i", str(input_scan),
    "-sd", str(output_dir),
    "-openmp", str(n_threads_max), # Maximum number of threads for this one subject
    "-time"
    ]

    if hemi_in_parallel:
        cmd += ["-parallel"]

    # --------------------------
    # Run MRIQC
    # --------------------------
    log.info(f"[{subject}] recon-all started")
    log.info("Logs will not be printed to this log file, go to Freesurfer output dir for subject-specific logs")
    
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log.error(f"[{subject}] recon-all failed:\n{result.stdout}")
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)

    log.info(f"[{subject}] recon-all completed successfully")

def main():
    # --------------------------
    # Argument parsing
    # --------------------------
    parser = argparse.ArgumentParser(
        description="Run Freesurfer on anatomical T1 scans for surface reconstruction."
    )

    # Standard arguments
    parser.add_argument("-c", "--config", required=True, help="Path to project YAML config file")
    parser.add_argument("-s", "--subjects", nargs="+", help="Space-separated list of subject IDs (optional)")
    parser.add_argument("-n", "--sessions", nargs="+", help="Space-separated list of session numbers (ignored in this module)")
    parser.add_argument("-r", "--runs", nargs="+", help="Space-separated list of run numbers (ignored in this module)")

    args = parser.parse_args()

    # --------------------------
    # Start timer
    # --------------------------
    start_time = datetime.now()
    log.info("Freesurfer module started")

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
    scratch_dir_freesurfer = scratch_dir / "MemoryLane" / "freesurfer"
    temp_anat_dir = scratch_dir_freesurfer / "anat"
    temp_output_dir_freesurfer = scratch_dir_freesurfer / "output"

    # Create the directories if they do not exist
    temp_anat_dir.mkdir(parents=True, exist_ok=True)
    temp_output_dir_freesurfer.mkdir(parents=True, exist_ok=True)

    # Copy the BIDS directory to scratch
    log.info("Copying anatomical scans of your desired subjects to scratch...\n")
    if args.subjects:
        sub_dict = {}
        for sub in args.subjects:
            scan_name = f"sub-{sub}_ses-1_T1w.nii.gz"
            t1_scan_src = bids_dir / f"sub-{sub}" / "ses-1" / "anat" / scan_name  # NB; Maybe change this, assumes too much about location and naming of T1w
            if not t1_scan_src.exists():
                log.warning(f"Warning: T1 scan not found for subject {sub} at {t1_scan_src}. Skipping subject.")
                continue
            t1_scan_dst = temp_anat_dir / scan_name
            log.info(f"Copying T1: {t1_scan_src} → {t1_scan_dst}")
            shutil.copyfile(t1_scan_src, t1_scan_dst)
            sub_dict[sub] = t1_scan_dst
        print("")
    else:
        raise Exception("No subjects specified to process") # NB; Maybe change this, to take all subjects from the config? See how I did that with MRIqc
  
    # ----------------------------------------------------------------------------------
    # Determine Parallellization; based on unit tests of processing speed given settings
    # ----------------------------------------------------------------------------------
    # Calculate parallelism based on CPUs and memory
    total_subjects = len(sub_dict)

    def allocate_resources(total_cores, mem_gb, n_subjects):
        for hemi, cores in [(True,8),(False,8),(False,4),(False,2)]:
            per_subj = cores * (2 if hemi else 1)
            max_subj = min(total_cores // per_subj, mem_gb // 4)
            if max_subj >= n_subjects:
                return {"cores_per_sub": cores if hemi else cores,
                        "parallel_hemi": hemi,
                        "subjects_in_parallel": n_subjects}
        # If not all subjects fit, run as many as possible in parallel
        hemi, cores = False, 2
        per_subj = cores
        max_subj = min(total_cores // per_subj, mem_gb // 4)
        return {"cores_per_sub": cores, "parallel_hemi": hemi,
                "subjects_in_parallel": max_subj}

    run_settings = allocate_resources(n_cpus, mem_gb, total_subjects)

    subjects_in_parallel = run_settings["subjects_in_parallel"]
    n_threads_max = run_settings["cores_per_sub"]
    hemi_in_parallel = run_settings["parallel_hemi"] 

    log.info(f"Max CPUs={n_cpus}, Max Mem={mem_gb}GB, total_subjects={total_subjects}")
    log.info(f"Running up to {subjects_in_parallel} subjects in parallel with {n_threads_max} threads/subject & 4GB memory/subject, hemispheric parallelization = {hemi_in_parallel}")
 
    # ------------------------------
    # Run Freesurfer in parallel
    # ------------------------------
    errors = {}
    with ThreadPoolExecutor(max_workers=subjects_in_parallel) as executor:
        futures = {
            executor.submit(run_recon_all, sub, sub_dict[sub], temp_output_dir_freesurfer, n_threads_max, hemi_in_parallel): sub
            for sub in sub_dict.keys()}

        for future in as_completed(futures):
            subject = futures[future]
            try:
                future.result()
            except Exception as e:
                errors[subject] = str(e)
    
    if errors:
        log.error(f"{len(errors)} subject(s) failed: {', '.join(errors.keys())}")
        raise RuntimeError("One or more Freesurfer runs failed. See logs above.")
    else:
        log.info("All subjects processed successfully")
    
    log.info("Finished running Freesurfer for all subjects!\n")
 
    # --------------------------
    # Postprocessing: move + cleanup
    # --------------------------
    final_output_dir_freesurfer = derivatives_dir / "freesurfer"
    log.info(f"Moving outputs from {temp_output_dir_freesurfer} → {final_output_dir_freesurfer}")
    copytree_gvfs(temp_output_dir_freesurfer, final_output_dir_freesurfer, remove_src=True, silent=False)

    log.info(f"Removing work directory {scratch_dir_freesurfer} to save space...")
    remove_dir(scratch_dir_freesurfer)

    log.info("Freesurfer processing complete. \n")
    log.info(f"Final outputs located at: {final_output_dir_freesurfer}")

    # --------------------------
    # End timer
    # --------------------------
    end_time = datetime.now()
    elapsed = end_time - start_time
    log.info(f"Elapsed time: {elapsed}")

if __name__ == "__main__":
    main()