#!/usr/bin/env python3
"""Test sync preparation without credentials, GitHub requests or real repository writes."""

from contextlib import redirect_stderr
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "prepare_review_rules_pr", ROOT / "scripts/prepare_review_rules_pr.py"
)
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)
sys.path.pop(0)


def git(root, *args):
    return (
        subprocess.check_output(
            ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args],
            stderr=subprocess.PIPE,
        )
        .decode()
        .strip()
    )


def commit_files(root, *names):
    git(root, "add", "--", *names)
    git(
        root,
        "-c",
        "user.name=Sync Test",
        "-c",
        "user.email=sync-test@example.invalid",
        "commit",
        "--no-gpg-sign",
        "-m",
        "test: record fixture",
    )


def snapshot(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


class SyncPreparationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="kanata-sync-pr-test-")
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.source = self.base / "source"
        self.target = self.base / "target"
        self.body = self.base / "review-pr.md"
        for root in (self.source, self.target):
            root.mkdir()
            git(root, "init", "--initial-branch=main")
        for name in [*prepare.sync.SECTIONS, "config/repositories.json"]:
            destination = self.source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        commit_files(self.source, "rules", "SOURCES.md", "config/repositories.json")
        self.revision = git(self.source, "rev-parse", "HEAD")
        (self.target / "README.md").write_text("unrelated content\n")
        commit_files(self.target, "README.md")

    def prepare(self, apply=True, revision=None, body=None):
        return prepare.prepare(
            self.source, self.target, revision or self.revision, body or self.body, apply
        )

    def commit_generated(self):
        files = prepare.sync.build_bundle(self.source, self.revision)
        commit_files(self.target, *files)

    def record_config(self, value):
        (self.source / "config/repositories.json").write_text(json.dumps(value))
        commit_files(self.source, "config/repositories.json")
        self.revision = git(self.source, "rev-parse", "HEAD")

    def test_matrix_selects_only_three_remote_targets(self):
        matrix = prepare.sync_matrix(self.source, self.revision)
        self.assertEqual(
            matrix,
            {
                "include": [
                    {"repository": f"YumaMatsumura/{name}", "name": name}
                    for name in ("kanata_common", "kanata_core", "kanata_operation")
                ]
            },
        )
        self.assertFalse((self.base / "src").exists())

    def test_matrix_reads_committed_config(self):
        (self.source / "config/repositories.json").write_text("uncommitted invalid data")
        self.assertEqual(len(prepare.sync_matrix(self.source, self.revision)["include"]), 3)

    def test_extra_candidate_is_not_automatically_written(self):
        config = json.loads((self.source / "config/repositories.json").read_text())
        config["repositories"].append({"name": "other", "github_repository": "someone/other"})
        self.record_config(config)
        self.assertEqual(len(prepare.sync_matrix(self.source, self.revision)["include"]), 3)

    def test_invalid_or_ambiguous_target_is_rejected(self):
        original = json.loads((self.source / "config/repositories.json").read_text())
        invalid = []
        for kind in ("missing", "duplicate", "repository", "base"):
            config = json.loads(json.dumps(original))
            if kind == "missing":
                config["repositories"].pop()
            elif kind == "duplicate":
                config["repositories"].append(config["repositories"][0])
            elif kind == "repository":
                config["repositories"][0]["github_repository"] = "owner/kanata_core"
            else:
                config["development_branch"] = "other"
            invalid.append(config)
        for config in invalid:
            with self.subTest(config=config):
                self.record_config(config)
                with self.assertRaises(prepare.sync.DistributionError):
                    prepare.sync_matrix(self.source, self.revision)

    def test_dry_run_does_not_write_target_or_body(self):
        before = snapshot(self.target)
        result = self.prepare(apply=False)
        self.assertEqual(result["changed"], "true")
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(self.body.exists())

    def test_initial_sync_generates_only_managed_paths_and_clear_body(self):
        before_head = git(self.target, "rev-parse", "HEAD")
        before_index = (self.target / ".git/index").read_bytes()
        result = self.prepare()
        names = set(result["add_paths"].splitlines())
        self.assertEqual(len(names), 9)
        self.assertEqual(set(snapshot(self.target)), names | {"README.md"})
        self.assertEqual((self.target / "README.md").read_text(), "unrelated content\n")
        self.assertEqual(git(self.target, "rev-parse", "HEAD"), before_head)
        self.assertEqual((self.target / ".git/index").read_bytes(), before_index)
        self.assertEqual(result["source_sha"], self.revision)
        body = self.body.read_text()
        self.assertIn("未導入", body)
        self.assertIn(self.revision, body)
        self.assertIn("AIによるレビューは実行していません", body)
        self.assertIn("lint・整形 | 未実施", body)
        self.assertEqual(body.count("## "), 5)

    def test_same_revision_after_merge_has_no_changes(self):
        self.prepare()
        self.commit_generated()
        before = snapshot(self.target)
        self.assertEqual(self.prepare()["changed"], "false")
        self.assertEqual(snapshot(self.target), before)

    def test_explicit_source_pin_and_later_update(self):
        self.prepare()
        self.commit_generated()
        old_revision = self.revision
        with (self.source / "rules/review.md").open("a") as stream:
            stream.write("\n新しい確認基準です。\n")
        commit_files(self.source, "rules/review.md")
        new_revision = git(self.source, "rev-parse", "HEAD")
        self.assertEqual(self.prepare(revision=old_revision)["changed"], "false")
        result = self.prepare(revision=new_revision)
        self.assertEqual(result["source_sha"], new_revision)
        self.assertIn(old_revision, self.body.read_text())
        self.assertIn(new_revision, self.body.read_text())
        self.assertIn(
            "新しい確認基準です。",
            (self.target / prepare.sync.BUNDLE / "rules/review.md").read_text(),
        )

    def test_moving_or_invalid_source_ref_is_rejected(self):
        for revision in ("HEAD", "main", "--help", "0" * 40):
            with self.subTest(revision=revision):
                with self.assertRaises(prepare.sync.DistributionError):
                    self.prepare(revision=revision)
        self.assertFalse(self.body.exists())

    def test_dirty_target_is_not_changed(self):
        (self.target / "README.md").write_text("user edits\n")
        before = snapshot(self.target)
        with self.assertRaisesRegex(prepare.sync.DistributionError, "変更のない"):
            self.prepare()
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(self.body.exists())

    def test_staged_or_untracked_files_are_not_changed(self):
        (self.target / "new.txt").write_text("user file\n")
        with self.assertRaises(prepare.sync.DistributionError):
            self.prepare()
        git(self.target, "add", "new.txt")
        before_index = (self.target / ".git/index").read_bytes()
        with self.assertRaises(prepare.sync.DistributionError):
            self.prepare()
        self.assertEqual((self.target / ".git/index").read_bytes(), before_index)

    def test_foreign_agents_are_preserved(self):
        (self.target / "AGENTS.md").write_text("existing instructions\n")
        commit_files(self.target, "AGENTS.md")
        before = snapshot(self.target)
        with self.assertRaises(prepare.sync.DistributionError):
            self.prepare()
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(self.body.exists())

    def test_committed_manual_edit_of_generated_rule_is_preserved(self):
        self.prepare()
        self.commit_generated()
        path = f"{prepare.sync.BUNDLE}/rules/review.md"
        (self.target / path).write_text("manually edited\n")
        commit_files(self.target, path)
        before = snapshot(self.target)
        with self.assertRaises(prepare.sync.DistributionError):
            self.prepare()
        self.assertEqual(snapshot(self.target), before)

    def test_body_cannot_be_written_into_a_repository(self):
        for root in (self.target, self.source):
            with self.subTest(root=root):
                with self.assertRaises(prepare.sync.DistributionError):
                    self.prepare(body=root / "pr.md")
                self.assertFalse((root / "pr.md").exists())

    def test_invalid_manifest_does_not_modify_checkout(self):
        self.prepare()
        self.commit_generated()
        path = self.target / prepare.sync.MANIFEST
        manifest = json.loads(path.read_bytes())
        manifest["source_commit"] = "not-a-commit"
        path.write_text(json.dumps(manifest))
        commit_files(self.target, prepare.sync.MANIFEST)
        before = snapshot(self.target)
        with self.assertRaises(prepare.sync.DistributionError):
            self.prepare()
        self.assertEqual(snapshot(self.target), before)

    def test_output_failure_happens_before_distribution(self):
        self.body.mkdir()
        before = snapshot(self.target)
        with self.assertRaises(OSError):
            self.prepare()
        self.assertEqual(snapshot(self.target), before)

    def test_outputs_preserve_multiline_path_list(self):
        values = self.prepare(apply=False)
        output = self.base / "github-output"
        prepare.write_outputs(output, values)
        content = output.read_text()
        self.assertIn(f"source_sha<<KANATA_OUTPUT\n{self.revision}\nKANATA_OUTPUT\n", content)
        self.assertIn("add_paths<<KANATA_OUTPUT\nAGENTS.md\n.github/kanata/review/", content)
        self.assertEqual(content.count("<<KANATA_OUTPUT"), 3)

    def test_matrix_cli_writes_outputs_without_target_repositories(self):
        output = self.base / "github-output"
        fake_script = self.source / "scripts/prepare_review_rules_pr.py"
        with patch.object(prepare, "__file__", str(fake_script)), redirect_stdout(io.StringIO()):
            self.assertEqual(prepare.main(["--matrix", "--github-output", str(output)]), 0)
        content = output.read_text()
        self.assertIn(self.revision, content)
        self.assertIn("YumaMatsumura/kanata_operation", content)
        self.assertFalse(self.body.exists())

    def test_matrix_cli_rejects_distribution_arguments(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                prepare.main(["--matrix", "--apply"])
        self.assertEqual(error.exception.code, 2)

    def test_distribution_cli_runs_without_extra_packages(self):
        scripts = self.source / "scripts"
        scripts.mkdir()
        for name in ("prepare_review_rules_pr.py", "sync_review_rules.py"):
            shutil.copyfile(ROOT / "scripts" / name, scripts / name)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(scripts / "prepare_review_rules_pr.py"),
                "--target",
                str(self.target),
                "--source-ref",
                self.revision,
                "--body-file",
                str(self.body),
                "--apply",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("APPLIED: changed=true", result.stdout)
        self.assertTrue(self.body.is_file())


if __name__ == "__main__":
    unittest.main()
