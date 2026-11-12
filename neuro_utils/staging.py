"""Copy data between the (slow, mounted) project drive and local scratch."""

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


def copy_tree(src, dst):
    """Copy the contents of src into dst, merging with what is there.

    Uses plain file copies (no permission/metadata copying), which is what
    works on the gvfs-mounted research drive; shutil.copytree does not.
    Symlinks are followed and copied as regular files/directories.
    """
    src, dst = Path(src), Path(dst)
    if not src.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            copy_tree(item, target)
        else:
            shutil.copyfile(item, target)


def stage_bids(bids_dir, dst, subjects):
    """Copy the top-level BIDS files plus only the requested subject folders."""
    bids_dir, dst = Path(bids_dir), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in bids_dir.iterdir():
        if item.is_file():
            shutil.copyfile(item, dst / item.name)
    for sub in subjects:
        copy_tree(bids_dir / f"sub-{sub}", dst / f"sub-{sub}")
    log.info("Staged BIDS top-level files + %d subject(s) to %s", len(subjects), dst)


def list_subjects(bids_dir):
    """Subject labels (without 'sub-') present in a BIDS directory."""
    return sorted(p.name.removeprefix("sub-") for p in Path(bids_dir).glob("sub-*") if p.is_dir())


def remove_tree(path):
    """Delete a scratch directory (symlinks are removed, never followed)."""
    path = Path(path)
    if path.exists():
        shutil.rmtree(path)
        log.info("Removed %s", path)
