#!/usr/bin/env python3
"""Test review-rule distribution in isolated temporary Git repositories."""

from contextlib import redirect_stderr
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sync_review_rules.py"
SPEC = importlib.util.spec_from_file_location("sync_review_rules", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


def run_git(root, *args):
    return (
        subprocess.check_output(
            ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args],
            stderr=subprocess.PIPE,
        )
        .decode()
        .strip()
    )


def snapshot(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


class DistributionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kanata-review-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.source = self.base / "workflow"
        self.target = self.base / "common"
        for repo in (self.source, self.target):
            repo.mkdir()
            run_git(repo, "init", "--initial-branch=main")
        for name in sync.SECTIONS:
            destination = self.source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        self.commit()
        self.revision = run_git(self.source, "rev-parse", "HEAD")
        self.files = sync.build_bundle(self.source, self.revision)

    def commit(self):
        run_git(self.source, "add", "rules", "SOURCES.md")
        run_git(
            self.source,
            "-c",
            "user.name=Review Test",
            "-c",
            "user.email=review-test@example.invalid",
            "commit",
            "--no-gpg-sign",
            "-m",
            "test: record source rules",
        )

    def apply(self, files=None):
        files = self.files if files is None else files
        sync.validate_target(self.target, self.source, files)
        sync.apply_changes(self.target, sync.plan_changes(self.target, files))

    def cli(self, *arguments):
        output = io.StringIO()
        # Only change the script's location for its documented source-root discovery.
        with (
            patch.object(sync, "__file__", str(self.source / "scripts/sync_review_rules.py")),
            redirect_stdout(output),
            redirect_stderr(output),
        ):
            script_copy = Path(sync.__file__)
            script_copy.parent.mkdir(exist_ok=True)
            shutil.copyfile(SCRIPT, script_copy)
            result = sync.main(["--target", str(self.target), *arguments])
        return result, output.getvalue()

    def test_dry_run_and_missing_check_do_not_write(self):
        before = snapshot(self.target)
        self.assertEqual(self.cli()[0], 0)
        self.assertEqual(snapshot(self.target), before)
        self.assertEqual(self.cli("--check")[0], 1)
        self.assertEqual(snapshot(self.target), before)

    def test_apply_and_check_without_other_repositories(self):
        self.assertEqual(self.cli("--apply")[0], 0)
        self.assertEqual(self.cli("--check")[0], 0)
        self.assertEqual(set(snapshot(self.target)), set(self.files))
        self.assertFalse((self.base / "core").exists())
        self.assertFalse((self.base / "operation").exists())

    def test_provenance_and_selected_sections(self):
        self.apply()
        manifest = json.loads((self.target / sync.MANIFEST).read_bytes())
        self.assertEqual(manifest["source_commit"], self.revision)
        self.assertEqual(
            manifest["generator_sha256"], hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        )
        for name, recorded in manifest["source_files"].items():
            self.assertEqual(
                recorded["sha256"], hashlib.sha256((self.source / name).read_bytes()).hexdigest()
            )
        common = (self.target / sync.BUNDLE / "rules/common.md").read_text()
        self.assertIn("## 変更を必要最小限にする", common)
        self.assertIn("## コマンドや実機を扱うとき", common)
        self.assertNotIn("## 作業を始めるとき", common)
        kanata = (self.target / sync.BUNDLE / "rules/kanata.md").read_text()
        self.assertNotIn("~/kanata_ws", kanata)
        for name, expected_hash in manifest["generated_files"].items():
            self.assertEqual(
                hashlib.sha256((self.target / name).read_bytes()).hexdigest(), expected_hash
            )

    def test_links_to_bundled_rules_and_pinned_background(self):
        self.apply()
        for name in self.files:
            if not name.endswith(".md"):
                continue
            path = self.target / name
            for match in sync.LINK.finditer(path.read_text()):
                destination = sync.urlsplit(match.group(2))
                if destination.scheme or destination.netloc or not destination.path:
                    continue
                self.assertTrue((path.parent / destination.path).exists(), (name, match.group(2)))
        common = (self.target / sync.BUNDLE / "rules/common.md").read_text()
        self.assertIn(f"{sync.SOURCE_URL}/blob/{self.revision}/rules/git.md", common)
        coding = (self.target / sync.BUNDLE / "rules/coding.md").read_text()
        self.assertIn("[SOURCES.md](../SOURCES.md)", coding)

    def test_idempotent_apply_preserves_files_and_git_index(self):
        (self.target / "unrelated.txt").write_text("keep\n")
        run_git(self.target, "add", "unrelated.txt")
        before_index = (self.target / ".git/index").read_bytes()
        self.apply()
        before = snapshot(self.target)
        self.assertEqual(sync.plan_changes(self.target, self.files), {})
        self.apply()
        self.assertEqual(snapshot(self.target), before)
        self.assertEqual((self.target / ".git/index").read_bytes(), before_index)
        self.assertEqual((self.target / "unrelated.txt").read_text(), "keep\n")

    def test_uncommitted_source_changes_are_not_distributed(self):
        (self.source / "rules/review.md").write_text("uncommitted rules\n")
        self.assertEqual(sync.build_bundle(self.source, "HEAD"), self.files)

    def test_explicit_source_pin_and_update(self):
        self.apply()
        with (self.source / "rules/review.md").open("a") as stream:
            stream.write("\n新しいレビュー基準の説明です。\n")
        self.commit()
        self.assertEqual(sync.build_bundle(self.source, self.revision), self.files)
        updated = sync.build_bundle(self.source, "HEAD")
        self.assertNotEqual(updated, self.files)
        self.apply(updated)
        self.assertEqual(snapshot(self.target), updated)

    def test_foreign_agents_file_is_not_overwritten(self):
        (self.target / "AGENTS.md").write_text("existing instructions\n")
        before = snapshot(self.target)
        with self.assertRaises(sync.DistributionError):
            self.apply()
        self.assertEqual(snapshot(self.target), before)

    def test_generated_edits_block_update_before_any_writes(self):
        self.apply()
        (self.target / sync.BUNDLE / "rules/review.md").write_text("local edits\n")
        before = snapshot(self.target)
        with self.assertRaises(sync.DistributionError):
            self.apply()
        self.assertEqual(snapshot(self.target), before)
        self.assertEqual(self.cli("--check")[0], 1)

    def test_missing_generated_file_can_be_recovered(self):
        self.apply()
        (self.target / sync.BUNDLE / "rules/review.md").unlink()
        self.apply()
        self.assertEqual(snapshot(self.target), self.files)

    def test_invalid_manifest_is_not_overwritten(self):
        self.apply()
        for invalid in ("invalid JSON", "[]", '{"generated_files": null}'):
            with self.subTest(invalid=invalid):
                (self.target / sync.MANIFEST).write_text(invalid)
                before = snapshot(self.target)
                with self.assertRaises(sync.DistributionError):
                    self.apply()
                self.assertEqual(snapshot(self.target), before)

    def test_override_file_blocks_distribution(self):
        (self.target / "AGENTS.override.md").write_text("overrides\n")
        with self.assertRaises(sync.DistributionError):
            self.apply()
        self.assertFalse((self.target / "AGENTS.md").exists())

    def test_symlinked_parent_and_entrypoint_are_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        for name in (".github", "AGENTS.md"):
            with self.subTest(name=name):
                link = self.target / name
                link.symlink_to(outside)
                with self.assertRaises(sync.DistributionError):
                    self.apply()
                link.unlink()
        self.assertEqual(list(outside.iterdir()), [])

    def test_partial_failure_removes_only_new_files(self):
        (self.target / ".github").mkdir()
        (self.target / ".github/existing.yml").write_text("keep\n")
        original_write = sync.atomic_write
        count = 0

        def fail_third_write(path, data):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError("simulated disk failure")
            original_write(path, data)

        before = snapshot(self.target)
        with patch.object(sync, "atomic_write", side_effect=fail_third_write):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(snapshot(self.target), before)
        self.assertFalse((self.target / ".github/kanata").exists())

    def test_failed_update_restores_previous_bundle(self):
        self.apply()
        before = snapshot(self.target)
        with (self.source / "rules/review.md").open("a") as stream:
            stream.write("\n追加の説明です。\n")
        with (self.source / "rules/coding.md").open("a") as stream:
            stream.write("\n追加の説明です。\n")
        self.commit()
        updated = sync.build_bundle(self.source, "HEAD")
        original_write = sync.atomic_write

        def fail_coding(path, data):
            if path.name == "coding.md" and data == updated[f"{sync.BUNDLE}/rules/coding.md"]:
                raise OSError("simulated disk failure")
            original_write(path, data)

        with patch.object(sync, "atomic_write", side_effect=fail_coding):
            with self.assertRaises(OSError):
                self.apply(updated)
        self.assertEqual(snapshot(self.target), before)

    def test_git_worktree_target_is_supported(self):
        (self.target / "README.md").write_text("fixture\n")
        run_git(self.target, "add", "README.md")
        run_git(
            self.target,
            "-c",
            "user.name=Review Test",
            "-c",
            "user.email=review-test@example.invalid",
            "commit",
            "--no-gpg-sign",
            "-m",
            "test: prepare target",
        )
        worktree = self.base / "worktree"
        run_git(self.target, "worktree", "add", "--detach", str(worktree))
        self.target = worktree
        self.apply()
        self.assertTrue((self.target / sync.MANIFEST).is_file())

    def test_invalid_targets_do_not_create_directories(self):
        missing = self.base / "missing"
        nested = self.target / "nested"
        nested.mkdir()
        for target in (missing, nested, self.source):
            with self.subTest(target=target):
                with self.assertRaises(sync.DistributionError):
                    sync.validate_target(target, self.source, self.files)
        self.assertFalse(missing.exists())

    def test_invalid_source_or_missing_section_fails(self):
        with self.assertRaises(sync.DistributionError):
            sync.build_bundle(self.source, "does-not-exist")
        (self.source / "rules/common.md").write_text("# Missing sections\n")
        self.commit()
        with self.assertRaises(sync.DistributionError):
            sync.build_bundle(self.source, "HEAD")
        self.assertEqual(snapshot(self.target), {})

    def test_code_examples_are_not_rewritten(self):
        content = "[Git](git.md)\n\n```markdown\n[Git](git.md)\n```\n"
        result = sync.rewrite_links(content, "rules/common.md", self.revision)
        self.assertIn(f"{self.revision}/rules/git.md", result)
        self.assertIn("```markdown\n[Git](git.md)\n```", result)


if __name__ == "__main__":
    unittest.main()
