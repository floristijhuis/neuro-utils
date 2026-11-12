"""FreeSurfer recon-all with the native install, several subjects in parallel.

Resource rule (as in v0): ~4 GB RAM per subject, at most 8 OpenMP threads per
subject. With -parallel, recon-all 7.3 runs lh and rh at the same time, each with
the -openmp thread count, so a subject then uses twice that many cores.
"""

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .staging import copy_tree, remove_tree

log = logging.getLogger(__name__)

DEFAULT_T1W_GLOB = "sub-{subject}/**/anat/sub-{subject}*_T1w.nii.gz"


def check_version(expected):
    """Refuse to run if recon-all is not the version the project YAML asks for."""
    out = subprocess.run(["recon-all", "-version"], capture_output=True, text=True).stdout.strip()
    if expected and expected not in out:
        raise RuntimeError(f"recon-all reports '{out}', but the project YAML expects {expected}")
    return out


def find_t1w(bids_dir, subject, pattern):
    matches = sorted(Path(bids_dir).glob(pattern.format(subject=subject)))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one T1w for sub-{subject} with '{pattern}', found "
                           f"{len(matches)}: {[m.name for m in matches]}. Set 'freesurfer: t1w_glob'.")
    return matches[0]


def allocate(n_cpus, mem_gb, n_subjects):
    """Return (subjects in parallel, OpenMP threads per subject, parallel hemispheres)."""
    max_by_mem = max(1, mem_gb // 4)
    for hemi, threads in [(True, 8), (False, 8), (False, 4), (False, 2)]:
        cores_per_subject = threads * (2 if hemi else 1)
        if min(n_cpus // cores_per_subject, max_by_mem) >= n_subjects:
            return n_subjects, threads, hemi
    return max(1, min(n_cpus // 2, max_by_mem)), 2, False


def recon_all_command(subject, t1w, subjects_dir, threads, hemi, extra_args):
    cmd = ["recon-all", "-all", "-s", f"sub-{subject}", "-i", t1w, "-sd", subjects_dir,
           "-openmp", threads]
    if hemi:
        cmd.append("-parallel")
    return [str(c) for c in cmd + list(extra_args)]


def _run_one(subject, cmd, env, subjects_dir):
    log.info("[sub-%s] recon-all started", subject)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-30:])
        log.error("[sub-%s] recon-all failed (full log: %s):\n%s", subject,
                  Path(subjects_dir) / f"sub-{subject}" / "scripts" / "recon-all.log", tail)
        raise subprocess.CalledProcessError(result.returncode, cmd)
    log.info("[sub-%s] recon-all finished", subject)


def freesurfer(project, subjects, sessions, extra_args, dry_run, stamp):
    settings = project.tool("freesurfer")
    final_dir = project.derivatives_dir / "freesurfer"
    pattern = settings.get("t1w_glob", DEFAULT_T1W_GLOB)
    if sessions:
        log.warning("Sessions are ignored for FreeSurfer; the T1w is selected with t1w_glob")

    todo = []
    for sub in subjects:
        sub_dir = final_dir / f"sub-{sub}"
        if (sub_dir / "scripts" / "recon-all.done").exists():
            log.info("[sub-%s] already reconstructed, skipping", sub)
        elif sub_dir.exists():
            raise RuntimeError(f"Unfinished FreeSurfer output in {sub_dir}; remove it to rerun.")
        else:
            todo.append(sub)
    if not todo:
        log.info("Nothing to do.")
        return

    t1w = {sub: find_t1w(project.bids_dir, sub, pattern) for sub in todo}
    n_parallel, threads, hemi = allocate(project.n_cpus, project.mem_gb, len(todo))
    log.info("%d subject(s): %d in parallel, %d OpenMP threads each, parallel hemispheres=%s",
             len(todo), n_parallel, threads, hemi)

    workspace = project.scratch_dir / project.name / f"freesurfer_{stamp}"
    subjects_dir = workspace / "subjects" if project.stage_data else final_dir
    commands = {sub: recon_all_command(sub, t1w[sub], subjects_dir, threads, hemi,
                                       [str(a) for a in settings.get("args") or []] + extra_args)
                for sub in todo}
    for sub, cmd in commands.items():
        log.info("[sub-%s] %s", sub, " ".join(cmd))
    if dry_run:
        return

    log.info("FreeSurfer version: %s", check_version(settings.get("version")))
    env = dict(os.environ, FS_LICENSE=str(project.fs_license))
    subjects_dir.mkdir(parents=True, exist_ok=True)

    failed = []
    with ThreadPoolExecutor(max_workers=n_parallel) as pool:
        futures = {pool.submit(_run_one, sub, cmd, env, subjects_dir): sub
                   for sub, cmd in commands.items()}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                failed.append(futures[future])

    if project.stage_data:
        # Copy back subject folders only; fsaverage is a symlink fMRIPrep recreates itself.
        for sub in todo:
            if sub not in failed:
                copy_tree(subjects_dir / f"sub-{sub}", final_dir / f"sub-{sub}")
    if failed:
        raise RuntimeError(f"recon-all failed for {sorted(failed)}; workspace kept: {workspace}")
    remove_tree(workspace)
