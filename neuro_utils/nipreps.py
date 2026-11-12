"""fMRIPrep and MRIQC (participant + group level) via their official Docker images.

Every run follows the same steps:
  1. build the container command from the project YAML + CLI selection,
  2. optionally stage the selected subjects to local scratch,
  3. run the container (work directory always on local scratch),
  4. copy outputs to <derivatives_dir>/<tool>, then delete the scratch workspace.
On failure the workspace is kept, so the work directory can be inspected/reused.
"""

import logging
from pathlib import Path

from .containers import docker_command, format_command, ensure_docker, ensure_image, image_version, run_logged
from .staging import copy_tree, remove_tree, stage_bids

log = logging.getLogger(__name__)

LICENSE = "/opt/freesurfer/license.txt"
FILTER = "/bids_filter.json"


class Job:
    """One container run: where things live on the host and how they are mounted."""

    def __init__(self, project, tool, stamp, image):
        self.project, self.tool, self.image = project, tool, image
        self.workspace = project.scratch_dir / project.name / f"{tool}_{stamp}"
        self.final_out = project.derivatives_dir / ("mriqc" if tool.startswith("mriqc") else tool)
        staged = project.stage_data
        self.bids = self.workspace / "bids" if staged else project.bids_dir
        self.out = self.workspace / "out" if staged else self.final_out
        self.work = self.workspace / "work"
        self.mounts = [(self.bids, "/data", True), (self.out, "/out", False),
                       (self.work, "/work", False)]
        self.args = []

    def add_filter_file(self):
        if self.project.bids_filter_file:
            self.mounts.append((self.project.bids_filter_file, FILTER, True))
            self.args += ["--bids-filter-file", FILTER]

    def command(self):
        return docker_command(self.image, self.mounts, self.args)

    def execute(self, dry_run, stage_in=(), stage_out=True):
        """Run the job; stage_in is a list of callables that fill the workspace."""
        cmd = self.command()
        log.info("Output directory: %s", self.final_out)
        log.info("Workspace: %s (staging %s)", self.workspace,
                 "on" if self.project.stage_data else "off")
        if dry_run:
            log.info("Dry run, would execute:\n%s", format_command(cmd))
            return
        ensure_docker()
        ensure_image(self.image)
        log.info("Tool version: %s", image_version(self.image))
        for prepare in stage_in:
            prepare()
        for path in (self.out, self.work):
            Path(path).mkdir(parents=True, exist_ok=True)
        try:
            run_logged(cmd)
        except Exception:
            log.error("%s failed; workspace kept for inspection: %s", self.tool, self.workspace)
            raise
        if self.project.stage_data and stage_out:
            log.info("Copying outputs %s -> %s", self.out, self.final_out)
            copy_tree(self.out, self.final_out)
        remove_tree(self.workspace)


def _required_image(project, tool):
    image = project.tool(tool).get("image")
    if not image:
        raise ValueError(f"Set '{tool}: image:' (e.g. nipreps/{tool}:<version>) in the project YAML")
    return image


def fmriprep(project, subjects, sessions, extra_args, dry_run, stamp):
    settings = project.tool("fmriprep")
    job = Job(project, "fmriprep", stamp, _required_image(project, "fmriprep"))
    job.mounts.append((project.fs_license, LICENSE, True))
    job.args = ["/data", "/out", "participant", "--participant-label", *subjects]
    if sessions:
        job.args += ["--session-label", *sessions]
    # fMRIPrep reads a bare number for --mem as MB, so give the unit explicitly
    job.args += ["-w", "/work", "--nprocs", project.n_cpus, "--omp-nthreads", project.omp_nthreads,
                 "--mem", f"{project.mem_gb}G", "--fs-license-file", LICENSE]
    job.add_filter_file()

    stage_in = []
    if project.stage_data:
        stage_in.append(lambda: stage_bids(project.bids_dir, job.bids, subjects))

    fs_dir = project.derivatives_dir / "freesurfer"
    if settings.get("reuse_freesurfer", True) and fs_dir.is_dir():
        # Only reuse finished reconstructions: an unfinished one would be completed
        # by fMRIPrep inside the (temporary) staged copy and then thrown away.
        unfinished = [s for s in subjects
                      if not (fs_dir / f"sub-{s}" / "scripts" / "recon-all.done").exists()]
        if unfinished:
            raise RuntimeError(f"No finished FreeSurfer output in {fs_dir} for: {unfinished}. "
                               "Run `neuro-utils freesurfer` first, or set reuse_freesurfer: false.")
        fs_mount = job.workspace / "freesurfer" if project.stage_data else fs_dir
        job.mounts.append((fs_mount, "/fs", False))  # fMRIPrep adds fsaverage here
        job.args += ["--fs-subjects-dir", "/fs"]
        if project.stage_data:
            stage_in += [lambda s=s: copy_tree(fs_dir / f"sub-{s}", fs_mount / f"sub-{s}")
                         for s in subjects]
        log.info("Reusing FreeSurfer reconstructions from %s", fs_dir)

    job.args += [str(a) for a in settings.get("args") or []] + extra_args
    job.execute(dry_run, stage_in)


def mriqc(project, subjects, sessions, extra_args, dry_run, stamp):
    settings = project.tool("mriqc")
    job = Job(project, "mriqc", stamp, _required_image(project, "mriqc"))
    job.args = ["/data", "/out", "participant", "--participant-label", *subjects]
    if sessions:
        job.args += ["--session-id", *sessions]
    # MRIQC's --mem is in GB
    job.args += ["-w", "/work", "--nprocs", project.n_cpus, "--omp-nthreads", project.omp_nthreads,
                 "--mem", project.mem_gb]
    job.add_filter_file()
    job.args += [str(a) for a in settings.get("args") or []] + extra_args

    stage_in = []
    if project.stage_data:
        stage_in.append(lambda: stage_bids(project.bids_dir, job.bids, subjects))
    job.execute(dry_run, stage_in)


def mriqc_group(project, subjects, sessions, extra_args, dry_run, stamp):
    """Group reports from existing participant-level MRIQC output."""
    settings = project.tool("mriqc")
    job = Job(project, "mriqc_group", stamp, _required_image(project, "mriqc"))
    if not job.final_out.is_dir():
        raise FileNotFoundError(f"No participant-level MRIQC output in {job.final_out}")
    job.args = ["/data", "/out", "group", "-w", "/work"]
    job.args += [str(a) for a in settings.get("group_args") or []] + extra_args

    stage_in = []
    if project.stage_data:
        stage_in += [lambda: stage_bids(project.bids_dir, job.bids, subjects),
                     lambda: copy_tree(job.final_out, job.out)]
    job.execute(dry_run, stage_in)
