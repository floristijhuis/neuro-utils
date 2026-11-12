"""Command line entry point: `neuro-utils <tool> -c project.yaml [options] [-- tool args]`.

Each call writes exactly one log file, <log_dir>/<timestamp>_<tool>.log, with the
command line, the project config, the tool version and the full tool output.
"""

import argparse
import logging
import sys
import time
from datetime import datetime

from . import __version__
from .config import load_project
from .freesurfer import freesurfer
from .nipreps import fmriprep, mriqc, mriqc_group
from .staging import list_subjects

TOOLS = {"freesurfer": freesurfer, "fmriprep": fmriprep,
         "mriqc": mriqc, "mriqc-group": mriqc_group}

log = logging.getLogger("neuro_utils")


def _setup_logging(log_file):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    for old in [h for h in log.handlers if getattr(h, "_neuro_utils", False)]:
        old.close()  # one log file per call, also when main() is called repeatedly
        log.removeHandler(old)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.FileHandler(log_file), logging.StreamHandler()):
        handler.setFormatter(fmt)
        handler._neuro_utils = True
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:  # everything after "--" goes to the tool unchanged
        extra = argv[argv.index("--") + 1:]
        argv = argv[:argv.index("--")]

    parser = argparse.ArgumentParser(prog="neuro-utils", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tool", choices=TOOLS)
    parser.add_argument("-c", "--config", required=True, help="project YAML")
    parser.add_argument("-s", "--subjects", nargs="+",
                        help="subject labels (default: YAML 'subjects', else all in bids_dir)")
    parser.add_argument("-n", "--sessions", nargs="+",
                        help="session labels (default: YAML 'sessions', else all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="only log what would run; nothing is copied or started")
    parser.add_argument("--version", action="version", version=f"neuro-utils {__version__}")
    args = parser.parse_args(argv)

    project = load_project(args.config)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _setup_logging(project.log_dir / f"{stamp}_{args.tool}{'_dryrun' if args.dry_run else ''}.log")

    subjects = [s.removeprefix("sub-") for s in args.subjects or project.subjects] \
        or list_subjects(project.bids_dir)
    sessions = [s.removeprefix("ses-") for s in args.sessions or project.sessions]

    log.info("neuro-utils %s: %s", __version__, " ".join(["neuro-utils", *sys.argv[1:]]))
    log.info("Project config %s:\n%s", args.config, open(args.config).read().rstrip())
    log.info("Subjects (%d): %s | sessions: %s", len(subjects), " ".join(subjects),
             " ".join(sessions) or "all")

    start = time.time()
    try:
        TOOLS[args.tool](project, subjects, sessions, extra, args.dry_run, stamp)
    except Exception:
        log.exception("%s failed after %.1f min", args.tool, (time.time() - start) / 60)
        return 1
    log.info("%s finished in %.1f min", args.tool, (time.time() - start) / 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
