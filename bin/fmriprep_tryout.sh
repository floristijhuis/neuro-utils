#!/bin/bash

IMAGE="nipreps/fmriprep:25.2.3"

echo "Checking to see if fMRIprep Docker image is properly configured..." 

# start rootless Docker if needed
if ! pgrep -u $USER dockerd-rootless > /dev/null; then
    nohup dockerd-rootless.sh -- > ~/.docker-rootless.log 2>&1 &
    sleep 5  # give it a few seconds to experimentalstart
fi

# Check if the fMRIprep Docker image is present, if not pull it
if ! docker image inspect $IMAGE > /dev/null 2>&1; then
    echo "fMRIprep Docker image not found locally. Pulling..."
    docker pull $IMAGE
fi

docker run --rm  \
  -v "/home/ftijhuis/projects/scratch/MemoryLane/fmriprep/bids":/data:ro \
  -v "/home/ftijhuis/projects/scratch/MemoryLane/fmriprep/output":/out \
  -v "/home/ftijhuis/projects/scratch/MemoryLane/fmriprep/work":/work \
  -v "/home/ftijhuis/projects/scratch/MemoryLane/fmriprep/freesurfer":/fs\
  -v "${FREESURFER_HOME}":/freesurfer \
  nipreps/fmriprep:25.2.3 \
  /data /out participant \
  --work-dir /work \
  --nprocs 16 \
  --mem_mb 64000 \
  --omp-nthreads 8 \
  --output-spaces MNI152NLin6Asym MNI152NLin2009cAsym T1w func fsnative fsaverage fsaverage5 fsaverage6 \
  --stop-on-first-crash \
  --verbose \
  --fs-subjects-dir /fs \
  --fs-license-file /freesurfer/license.txt