# neuro-utils

Small wrappers to run **FreeSurfer**, **fMRIPrep** and **MRIQC** on a BIDS dataset,
configured by one project YAML. Outputs go to `<derivatives_dir>/<tool>`.

```
neuro-utils freesurfer   -c project.yaml [-s SUB ...]
neuro-utils fmriprep     -c project.yaml [-s SUB ...] [-n SES ...] [-- extra fmriprep args]
neuro-utils mriqc        -c project.yaml [-s SUB ...] [-n SES ...] [-- extra mriqc args]
neuro-utils mriqc-group  -c project.yaml
```

`--dry-run` logs the exact commands without copying or running anything. Use it to check a
configuration, or to get the literal fMRIPrep/MRIQC call for a methods section.

## Install

```bash
pip install -e /path/to/neuro-utils     # inside the conda env you use for processing
```

Requirements: Python ≥ 3.10 with PyYAML; Docker (rootless Docker is started automatically
if it is not running); a native FreeSurfer install for `freesurfer`; a FreeSurfer license.

## Project YAML

See [`examples/project.yaml`](examples/project.yaml). The tool versions (`image:`, FreeSurfer
`version:`) and all tool-specific flags (`args:`) live in the project YAML, not in this
repository, so the YAML is the record of how a dataset was processed.

**Selecting data**
- Subjects: `-s` on the command line, else `subjects:` in the YAML, else all in `bids_dir`.
- Sessions: `-n`, else `sessions:`, else all. Passed as `--session-label` (fMRIPrep) and
  `--session-id` (MRIQC). FreeSurfer ignores sessions and uses `freesurfer: t1w_glob`.
- Runs, acquisitions, etc.: the `bids_filter_file` (keys `t1w`, `bold`, `fmap`, ...).
  It must **not** contain `subject` or `session`, and values must be strings
  (`"run": ["1", "2"]`). neuro-utils checks both, because
  fMRIPrep 25.2.3 fails on either (`Conflicting entities for "subject"` / a `TypeError`), and
  MRIQC 24 silently lets a filter's `subject`/`session` override the command line.

## What a run does

1. Writes one log file: `<log_dir>/<timestamp>_<tool>.log` (default `log_dir` is
   `<derivatives_dir>/logs`), with the command line, the YAML, the tool version and
   all tool output.
2. If `stage_data: true`, copies the top-level BIDS files and only the selected subjects to
   `<scratch_dir>/<project>/<tool>_<timestamp>/` (and, for fMRIPrep, their finished FreeSurfer
   folders). The tool's work directory is always on scratch.
3. Runs the tool, copies its outputs to `<derivatives_dir>/<tool>`, and deletes the workspace.
   **If the tool fails, the workspace is kept** for inspection; delete it yourself afterwards.

Run long jobs detached; the log file already has all the output:

```bash
setsid nohup neuro-utils fmriprep -c project.yaml > /dev/null 2>&1 &
```

`setsid` gives the run its own process group, which makes stopping it clean:

```bash
pgrep -af neuro-utils          # PID of the run (= its process group ID with setsid)
kill -- -<PID>                 # stops neuro-utils, recon-all and all their child processes
docker ps; docker stop <id>    # containers are not children of neuro-utils: stop them too
```

Killing only `neuro-utils` or `recon-all` leaves recon-all's child programs (`mri_*`, ANTs)
running.

## Tool notes

**FreeSurfer** (`recon-all -all`, native install). Refuses to run if `recon-all -version` does
not contain `freesurfer: version`. Subjects with `scripts/recon-all.done` are skipped; an
unfinished subject folder must be removed before rerunning. Subjects run in parallel
(~4 GB RAM and at most 8 OpenMP threads per subject; `-parallel` hemispheres when there are
enough cores, which doubles the cores per subject); see `neuro_utils/freesurfer.py`.

**fMRIPrep**. `--nprocs`, `--omp-nthreads` and `--mem` come from `resources:` (memory is
passed as `<mem_gb>G`; a bare number would be read as MB). With `reuse_freesurfer: true`,
finished reconstructions in `<derivatives_dir>/freesurfer` are passed as `--fs-subjects-dir`;
neuro-utils stops if a selected subject has no finished reconstruction there.

**MRIQC**. `--mem` is in GB here. `mriqc-group` needs participant-level output in
`<derivatives_dir>/mriqc`, and MRIQC 24 needs the subject folders present in the BIDS
input even at group level, so these are staged too.

## Tests

```bash
python -m unittest discover tests
```

These check the configuration rules and the generated commands; they need neither Docker nor
FreeSurfer.

## History

`v0-legacy` (git tag) is the earlier `pipeline.py` + module scripts + bash-wrapper version.
