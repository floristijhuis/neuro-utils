"""Load and validate a project YAML (see examples/project.yaml)."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# fMRIPrep 25.2.3 (niworkflows 1.14.2) raises "Conflicting entities" if a filter
# file sets these, and MRIQC 24 silently lets them override the CLI selection.
# Subjects and sessions are therefore only ever selected on the command line.
RESERVED_FILTER_ENTITIES = ("subject", "session")


@dataclass
class Project:
    name: str
    bids_dir: Path
    derivatives_dir: Path
    scratch_dir: Path
    stage_data: bool
    log_dir: Path
    fs_license: Path
    n_cpus: int
    mem_gb: int
    omp_nthreads: int
    subjects: list = field(default_factory=list)
    sessions: list = field(default_factory=list)
    bids_filter_file: Path | None = None
    tools: dict = field(default_factory=dict)

    def tool(self, name):
        """Settings section for one tool (empty dict if absent)."""
        return self.tools.get(name) or {}


def _default_license():
    if os.environ.get("FS_LICENSE"):
        return os.environ["FS_LICENSE"]
    return str(Path(os.environ.get("FREESURFER_HOME", "/usr/local/freesurfer")) / "license.txt")


def check_bids_filter(path):
    """Refuse filter files that select subjects or sessions."""
    filters = json.loads(Path(path).read_text())
    offending = {(query, entity) for query, entities in filters.items()
                 for entity in RESERVED_FILTER_ENTITIES if entity in entities}
    if offending:
        listed = ", ".join(f"{q}.{e}" for q, e in sorted(offending))
        raise ValueError(
            f"BIDS filter file {path} sets {listed}. Select subjects/sessions with "
            "-s/-n (or 'subjects'/'sessions' in the project YAML) instead; "
            "the filter file is only for runs, acquisitions, etc.")
    # fMRIPrep 25.2.3 crashes on numbers here (TypeError in config._process_value)
    numeric = sorted(f"{q}.{e}" for q, entities in filters.items() for e, v in entities.items()
                     if any(isinstance(x, (int, float)) for x in (v if isinstance(v, list) else [v])))
    if numeric:
        raise ValueError(f"BIDS filter file {path}: write values as strings, e.g. \"run\": [\"1\"] "
                         f"(numbers in {', '.join(numeric)})")


def load_project(path):
    """Read a project YAML into a Project, with defaults and sanity checks."""
    path = Path(path)
    cfg = yaml.safe_load(path.read_text())

    for key in ("bids_dir", "derivatives_dir", "scratch_dir"):
        if not cfg.get(key):
            raise ValueError(f"'{key}' is required in {path}")

    resources = cfg.get("resources") or {}
    derivatives_dir = Path(cfg["derivatives_dir"])
    project = Project(
        name=cfg.get("project", path.stem),
        bids_dir=Path(cfg["bids_dir"]),
        derivatives_dir=derivatives_dir,
        scratch_dir=Path(cfg["scratch_dir"]),
        stage_data=bool(cfg.get("stage_data", True)),
        log_dir=Path(cfg.get("log_dir") or derivatives_dir / "logs"),
        fs_license=Path(cfg.get("fs_license") or _default_license()),
        n_cpus=int(resources.get("n_cpus", 8)),
        mem_gb=int(resources.get("mem_gb", 32)),
        omp_nthreads=int(resources.get("omp_nthreads", 8)),
        subjects=[str(s).removeprefix("sub-") for s in cfg.get("subjects") or []],
        sessions=[str(s).removeprefix("ses-") for s in cfg.get("sessions") or []],
        bids_filter_file=Path(cfg["bids_filter_file"]) if cfg.get("bids_filter_file") else None,
        tools={k: cfg.get(k) for k in ("freesurfer", "fmriprep", "mriqc")},
    )

    if not project.bids_dir.is_dir():
        raise FileNotFoundError(f"BIDS directory not found: {project.bids_dir}")
    if project.bids_filter_file:
        check_bids_filter(project.bids_filter_file)
    return project
