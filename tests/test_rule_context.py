"""Check rule provenance using temporary files and repositories, without network access."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/kanata-error-review/scripts/collect_rule_context.py"
SPEC = importlib.util.spec_from_file_location("collect_rule_context", SCRIPT)
context_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(context_module)


def git(root: Path, *args: str) -> str:
    return (
        subprocess.check_output(
            ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args],
            stderr=subprocess.PIPE,
        )
        .decode()
        .strip()
    )


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class RuleContextTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="kanata rule context ")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "workflow"
        self.root.mkdir()
        self.write_rules(self.root)
        git(self.root, "init", "--initial-branch=main")
        self.commit()

    def write_rules(self, root: Path) -> None:
        names = [
            "AGENTS.md",
            "rules/common.md",
            "rules/kanata.md",
            "rules/communication.md",
            "rules/review.md",
            "rules/error-review.md",
            "rules/coding.md",
            "rules/testing.md",
            "skills/kanata-error-review/SKILL.md",
        ]
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# Test rule: {name}\n", encoding="utf-8")
        script = root / "skills/kanata-error-review/scripts/collect_rule_context.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SCRIPT, script)

    def commit(self) -> None:
        git(self.root, "add", "AGENTS.md", "rules", "skills/kanata-error-review")
        git(
            self.root,
            "-c",
            "user.name=Rule Context Test",
            "-c",
            "user.email=rule-context-test@example.invalid",
            "commit",
            "--no-gpg-sign",
            "-m",
            "test: record fixture rules",
        )

    def run_cli(self, root: Path | None = None) -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--workflow-root", str(root or self.root)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotIn("Traceback", result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_clean_context_hashes_and_no_writes(self) -> None:
        before = snapshot(self.root)
        code, result = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(result["source_commit"], git(self.root, "rev-parse", "HEAD"))
        self.assertFalse(result["has_local_changes"])
        self.assertEqual(result["git_status"], [])
        self.assertEqual(result["warnings"], [])
        for name, entry in result["files"].items():
            expected = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
            self.assertEqual(entry["sha256"], expected)
            self.assertEqual(entry["head_sha256"], expected)
            self.assertEqual(entry["state"], "clean")
        self.assertEqual(before, snapshot(self.root))

    def test_modified_and_untracked_rules_are_distinguished(self) -> None:
        path = self.root / "rules/error-review.md"
        content = path.read_bytes()
        git(self.root, "rm", "rules/error-review.md")
        self.commit()
        path.write_bytes(content)
        (self.root / "rules/coding.md").write_text("# Changed rule\n", encoding="utf-8")
        before = snapshot(self.root)
        code, result = self.run_cli()
        self.assertEqual(code, 0)
        self.assertTrue(result["has_local_changes"])
        self.assertEqual(result["files"]["rules/error-review.md"]["state"], "not_in_head")
        self.assertIsNone(result["files"]["rules/error-review.md"]["head_sha256"])
        self.assertEqual(result["files"]["rules/coding.md"]["state"], "modified")
        self.assertEqual(before, snapshot(self.root))

    def test_unrelated_changes_do_not_mark_rules_dirty(self) -> None:
        (self.root / "unrelated.txt").write_text("Unrelated user work\n", encoding="utf-8")
        code, result = self.run_cli()
        self.assertEqual(code, 0)
        self.assertFalse(result["has_local_changes"])

    def test_staged_changes_are_reported_even_when_worktree_matches_head(self) -> None:
        path = self.root / "rules/coding.md"
        original = path.read_bytes()
        path.write_text("# Staged rule\n", encoding="utf-8")
        git(self.root, "add", "rules/coding.md")
        path.write_bytes(original)
        before = snapshot(self.root)
        _, result = self.run_cli()
        self.assertTrue(result["has_local_changes"])
        self.assertTrue(result["git_status"])
        self.assertEqual(result["files"]["rules/coding.md"]["state"], "clean")
        self.assertEqual(before, snapshot(self.root))

    def test_missing_required_rule_returns_json_and_failure(self) -> None:
        (self.root / "rules/error-review.md").unlink()
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIsNone(result["files"]["rules/error-review.md"]["sha256"])
        self.assertEqual(result["files"]["rules/error-review.md"]["state"], "unreadable")
        self.assertTrue(result["warnings"])

    def test_copied_rules_without_git_keep_hashes_but_no_fake_version(self) -> None:
        copied = self.base / "copied rules"
        self.write_rules(copied)
        before = snapshot(copied)
        code, result = self.run_cli(copied)
        self.assertEqual(code, 0)
        self.assertIsNone(result["source_commit"])
        self.assertIsNone(result["has_local_changes"])
        self.assertTrue(result["files"]["rules/error-review.md"]["sha256"])
        self.assertTrue(result["warnings"])
        self.assertEqual(before, snapshot(copied))

    def test_parent_repository_commit_is_not_used_for_a_copy(self) -> None:
        copied = self.root / "copied rules"
        self.write_rules(copied)
        _, result = self.run_cli(copied)
        self.assertIsNone(result["source_commit"])
        self.assertIsNone(result["has_local_changes"])
        self.assertTrue(result["warnings"])

    def test_git_unavailable_does_not_claim_clean_committed_rules(self) -> None:
        with patch.object(context_module, "git", return_value=None):
            result = context_module.collect(self.root)
        self.assertIsNone(result["source_commit"])
        self.assertIsNone(result["has_local_changes"])
        self.assertTrue(result["warnings"])
        self.assertTrue(result["files"]["rules/review.md"]["sha256"])

    def test_default_root_resolves_the_real_script_through_a_symlink(self) -> None:
        source = self.root / "skills/kanata-error-review/scripts/collect_rule_context.py"
        entrypoint = self.base / "collect.py"
        entrypoint.symlink_to(source)
        result = subprocess.run(
            [sys.executable, "-B", str(entrypoint)], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)
        self.assertEqual(context["source_root"], str(self.root))
        self.assertFalse(context["has_local_changes"])


if __name__ == "__main__":
    unittest.main()
