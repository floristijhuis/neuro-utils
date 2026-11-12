"""Unit tests that need neither Docker nor FreeSurfer: `python -m unittest discover tests`."""

import json
import logging
import tempfile
import unittest
from pathlib import Path

import yaml

from neuro_utils.cli import main
from neuro_utils.config import load_project
from neuro_utils.freesurfer import allocate, find_t1w, recon_all_command


def make_project(tmp, filters=None, **overrides):
    """Minimal BIDS tree + project YAML in tmp; returns the YAML path."""
    tmp = Path(tmp)
    for sub in ("01", "02"):
        anat = tmp / "bids" / f"sub-{sub}" / "ses-1" / "anat"
        anat.mkdir(parents=True)
        (anat / f"sub-{sub}_ses-1_T1w.nii.gz").touch()
    (tmp / "bids" / "dataset_description.json").write_text("{}")
    cfg = {"project": "Test", "bids_dir": str(tmp / "bids"), "derivatives_dir": str(tmp / "deriv"),
           "scratch_dir": str(tmp / "scratch"), "fs_license": str(tmp / "license.txt"),
           "resources": {"n_cpus": 16, "mem_gb": 64, "omp_nthreads": 8},
           "fmriprep": {"image": "nipreps/fmriprep:25.2.3", "args": ["--use-syn-sdc"]},
           "mriqc": {"image": "nipreps/mriqc:24.0.2", "args": ["--no-sub"]},
           "freesurfer": {"version": "7.3.0"}}
    if filters is not None:
        (tmp / "filter.json").write_text(json.dumps(filters))
        cfg["bids_filter_file"] = str(tmp / "filter.json")
    cfg.update(overrides)
    path = tmp / "project.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path


def dry_run_log(argv):
    """Run the CLI in dry-run mode and return everything it logged."""
    with tempfile.TemporaryDirectory() as tmp, \
            unittest.TestCase().assertLogs("neuro_utils", logging.INFO) as logs:
        assert main(["--dry-run"] + argv) == 0
    return "\n".join(logs.output)


class ConfigTests(unittest.TestCase):
    def test_filter_with_subject_or_session_is_rejected(self):
        for entity in ("subject", "session"):
            with tempfile.TemporaryDirectory() as tmp:
                path = make_project(tmp, {"bold": {entity: ["01"], "suffix": "bold"}})
                with self.assertRaisesRegex(ValueError, f"bold.{entity}"):
                    load_project(path)

    def test_filter_with_numbers_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "as strings"):
                load_project(make_project(tmp, {"bold": {"run": [1, 2]}}))

    def test_filter_with_run_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = load_project(make_project(tmp, {"bold": {"run": ["1", "2"]}}))
            self.assertEqual(project.bids_filter_file.name, "filter.json")
            self.assertEqual(project.log_dir, Path(tmp) / "deriv" / "logs")


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.yaml = str(make_project(self.tmp.name, {"bold": {"run": ["1"]}}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_fmriprep_command(self):
        out = dry_run_log(["fmriprep", "-c", self.yaml, "-s", "sub-01", "-n", "1", "2",
                           "--", "--boilerplate-only"])
        for expected in ["--participant-label 01 \\", "--session-label", "--mem 64G",
                         "--bids-filter-file /bids_filter.json", "--use-syn-sdc",
                         "--boilerplate-only", "license.txt:/opt/freesurfer/license.txt:ro"]:
            self.assertIn(expected, out)
        self.assertNotIn("--fs-subjects-dir", out)  # no derivatives/freesurfer yet

    def test_fmriprep_refuses_unfinished_freesurfer(self):
        (Path(self.tmp.name) / "deriv" / "freesurfer" / "sub-01").mkdir(parents=True)
        with self.assertLogs("neuro_utils", logging.ERROR) as logs:
            self.assertEqual(main(["--dry-run", "fmriprep", "-c", self.yaml, "-s", "01"]), 1)
        self.assertIn("No finished FreeSurfer output", "\n".join(logs.output))

    def test_fmriprep_reuses_finished_freesurfer(self):
        done = Path(self.tmp.name) / "deriv" / "freesurfer" / "sub-01" / "scripts"
        done.mkdir(parents=True)
        (done / "recon-all.done").touch()
        out = dry_run_log(["fmriprep", "-c", self.yaml, "-s", "01"])
        self.assertIn("--fs-subjects-dir", out)
        self.assertIn("/freesurfer:/fs", out)  # staged copy, writable

    def test_mriqc_command_uses_gb_and_session_id(self):
        out = dry_run_log(["mriqc", "-c", self.yaml, "-n", "2"])
        self.assertIn("--participant-label 01 02 \\", out)  # all subjects by default
        self.assertIn("--session-id 2 \\", out)
        self.assertIn("--mem 64 \\", out)
        self.assertIn("--no-sub", out)

    def test_no_staging_mounts_project_folders(self):
        yaml_path = make_project(Path(self.tmp.name) / "nostage", stage_data=False)
        out = dry_run_log(["mriqc", "-c", str(yaml_path)])
        self.assertIn(f"{Path(self.tmp.name) / 'nostage' / 'bids'}:/data:ro", out)


class DockerCommandTests(unittest.TestCase):
    def test_paths_with_colons_are_refused(self):
        from neuro_utils.containers import docker_command
        with self.assertRaisesRegex(ValueError, "symlink"):
            docker_command("img", [("/run/user/1/gvfs/smb-share:server=x/data", "/data", True)], [])


class FreeSurferTests(unittest.TestCase):
    def test_allocate(self):
        self.assertEqual(allocate(16, 64, 1), (1, 8, True))    # 16 cores for one subject
        self.assertEqual(allocate(16, 64, 2), (2, 8, False))
        self.assertEqual(allocate(16, 64, 20), (8, 2, False))  # cores, not memory, limit
        self.assertEqual(allocate(32, 8, 20), (2, 2, False))   # memory limits (4 GB/subject)
        self.assertEqual(allocate(1, 2, 3), (1, 2, False))     # never zero workers

    def test_find_t1w_and_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_project(tmp)
            t1 = find_t1w(Path(tmp) / "bids", "01", "sub-{subject}/**/anat/sub-{subject}*_T1w.nii.gz")
            cmd = recon_all_command("01", t1, "/sd", 8, True, ["-time"])
            self.assertEqual(cmd[:4], ["recon-all", "-all", "-s", "sub-01"])
            self.assertIn("-parallel", cmd)
            self.assertEqual(cmd[-1], "-time")
            with self.assertRaisesRegex(RuntimeError, "found 0"):
                find_t1w(Path(tmp) / "bids", "99", "sub-{subject}/**/anat/*_T1w.nii.gz")


if __name__ == "__main__":
    unittest.main()
