#!/bin/bash
## Usage: Wrapper for running MRIqc based on Docker image. See https://mriqc.readthedocs.io/en/stable/ for more information. Due to portability, the wrapper contains some extra functionality to
## make sure that the docker daemon is activated and the image is pulled into the local system if not already present. This is necessary on Tux17 (rootless Docker setup).

## Usage example:
## bash mriqc_wrapper.sh <bids_dir> <output_dir> <scratch_dir> "<sub-01 sub-02 ...>" "<ses-01 ses-02 ...>" "<run-01 run-02 ...>" <n_cpus> <mem_gb>

BIDS_DIR=$1
OUT_DIR=$2
WORK_DIR=$3
NPROCS=${4:-16}
MEM_GB=${5:-64}

IMAGE="nipreps/mriqc:24.0.2"

echo "Checking to see if MRIqc Docker image is properly configured..." 

# start rootless Docker if needed
if ! pgrep -u $USER dockerd-rootless > /dev/null; then
    nohup dockerd-rootless.sh --experimental > ~/.docker-rootless.log 2>&1 &
    sleep 5  # give it a few seconds to start
fi

# Check if the MRIqc image is present, if not pull it
if ! docker image inspect $IMAGE > /dev/null 2>&1; then
    echo "MRIQC Docker image not found locally. Pulling..."
    docker pull $IMAGE
fi

echo "Running MRIqc with the following settings..."
echo "BIDS directory: $BIDS_DIR"
echo "Output directory: $OUT_DIR"
echo "Working directory: $WORK_DIR"
echo "Number of processors: $NPROCS"
echo "Memory (GB): $MEM_GB"
echo ""

# Run MRIqc command; This might be adjusted per project if specific options are needed or should be added.
# Per-line options:
  # Mount input directory as read-only
  # Mount output directory
  # Mount working directory
  # Positional arguments; Create another script for group level (?). 

docker run --rm  \
  -v "${BIDS_DIR}":/data:ro \
  -v "${OUT_DIR}":/out \
  -v "${WORK_DIR}":/work \
  $IMAGE \
  /data /out participant \
  --work-dir /work \
  --bids-filter-file /data/bids_filter_file.json \
  --nprocs ${NPROCS} \
  --mem_gb ${MEM_GB} \
  --verbose \
  --no-sub