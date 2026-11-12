"""Run tools with (rootless) Docker and stream their output into the log."""

import logging
import shlex
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)


def run_logged(cmd, env=None):
    """Run a command, writing each output line to the log; raise on failure."""
    log.info("Running: %s", " ".join(str(c) for c in cmd))
    proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)
    for line in proc.stdout:
        log.info("  %s", line.rstrip())
    if proc.wait() != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def _docker_ok():
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def ensure_docker(timeout=60):
    """Make sure the Docker daemon answers; start the rootless daemon if needed."""
    if _docker_ok():
        return
    if not shutil.which("dockerd-rootless.sh"):
        raise RuntimeError("Docker daemon is not running and dockerd-rootless.sh was not found.")
    log.info("Starting rootless Docker daemon (log: ~/.docker-rootless.log)")
    with open(Path.home() / ".docker-rootless.log", "a") as fh:
        subprocess.Popen(["dockerd-rootless.sh"], stdout=fh, stderr=subprocess.STDOUT,
                         start_new_session=True)
    for _ in range(timeout):
        if _docker_ok():
            return
        time.sleep(1)
    raise RuntimeError("Rootless Docker daemon did not come up; see ~/.docker-rootless.log")


def ensure_image(image):
    """Pull the image if it is not available locally."""
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
        log.info("Pulling %s", image)
        run_logged(["docker", "pull", image])


def image_version(image):
    """The tool's own --version output, for the log."""
    out = subprocess.run(["docker", "run", "--rm", image, "--version"],
                         capture_output=True, text=True)
    # The version is printed on stdout; upgrade notices go to stderr
    lines = out.stdout.strip().splitlines() or out.stderr.strip().splitlines()
    return lines[-1].strip() if lines else "unknown"


def format_command(cmd):
    """Shell-pasteable command with each option and its values on one line."""
    lines = [[]]
    for token in (shlex.quote(str(t)) for t in cmd):
        if token.startswith("-") and lines[-1]:
            lines.append([])
        lines[-1].append(token)
    return " \\\n    ".join(" ".join(line) for line in lines)


def docker_command(image, mounts, args):
    """Build a `docker run` command; mounts are (host_path, container_path, read_only)."""
    cmd = ["docker", "run", "--rm"]
    for host, container, read_only in mounts:
        if ":" in str(host):
            # e.g. a resolved gvfs path (.../smb-share:server=...); use the symlink instead
            raise ValueError(f"Docker cannot mount a path containing ':' : {host}. "
                             "Use a path without colons, e.g. a symlink such as ~/research_drive.")
        cmd += ["-v", f"{host}:{container}{':ro' if read_only else ''}"]
    return cmd + [image] + [str(a) for a in args]
