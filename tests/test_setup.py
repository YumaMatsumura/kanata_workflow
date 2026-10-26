"""Filesystem safety tests; never use a real KANATA checkout or network."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]


def snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    result = {}
    for path in sorted(root.rglob("*")):
        key = str(path.relative_to(root))
        if path.is_symlink():
            result[key] = ("link", os.readlink(path))
        elif path.is_file():
            result[key] = ("file", path.read_bytes())
        elif path.is_dir():
            result[key] = ("directory", "")
    return result


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="kanata workflow test ")
        self.base = Path(self.tmp.name)
        self.ws = self.base / "kanata workspace"
        self.ws.mkdir()
        self.src = self.ws / "src"
        self.src.mkdir()
        repo = self.src / "kanata_common"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (repo / "existing.cpp").write_text("// Existing user work; keep unchanged.\n")
        self.workflow = self.ws / "kanata_workflow"
        self.workflow.mkdir()
        # Copy only setup inputs; unrelated tools and local files are not fixtures.
        for name in ("AGENTS.md", "scripts/setup.py", "config/repositories.json"):
            target = self.workflow / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / name, target)
        shutil.copytree(SOURCE / "skills", self.workflow / "skills")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_setup(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(self.workflow / "scripts" / "setup.py"),
                "--workspace",
                str(self.ws),
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_default_is_read_only(self) -> None:
        before = snapshot(self.ws)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLAN (no writes)", result.stdout)
        self.assertEqual(before, snapshot(self.ws))

    def test_optional_repository_layouts(self) -> None:
        layouts = (
            (),
            ("kanata_common",),
            ("kanata_common", "kanata_core"),
            ("kanata_common", "kanata_operation"),
            ("kanata_common", "kanata_core", "kanata_operation"),
        )
        for names in layouts:
            with self.subTest(repositories=names):
                shutil.rmtree(self.src)
                self.src.mkdir()
                for name in names:
                    (self.src / name / ".git").mkdir(parents=True)
                    (self.src / name / "existing.cpp").write_text("// Keep user work.\n")
                before_src = snapshot(self.src)
                before_plan = snapshot(self.ws)
                plan = self.run_setup()
                self.assertEqual(plan.returncode, 0, plan.stderr)
                self.assertEqual(before_plan, snapshot(self.ws))
                for mode in ("--apply", "--check"):
                    result = self.run_setup(mode)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("WARNING:", result.stdout)
                    self.assertEqual(result.stdout.count("[PRESENT]"), len(names))
                    self.assertEqual(result.stdout.count("[NOT PLACED]"), 3 - len(names))
                    self.assertEqual(before_src, snapshot(self.src))
                self.assertNotIn("WARNING:", plan.stdout)
                self.assertEqual(sorted(p.name for p in self.src.iterdir()), sorted(names))

    def test_present_directory_without_git_is_reported_without_writes(self) -> None:
        shutil.rmtree(self.src / "kanata_common" / ".git")
        before = snapshot(self.ws)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING: no .git entry", result.stdout)
        self.assertEqual(before, snapshot(self.ws))

    def test_present_file_instead_of_repository_is_reported_without_writes(self) -> None:
        (self.src / "kanata_core").write_text("Existing file\n")
        before = snapshot(self.ws)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING: expected a repository directory", result.stdout)
        self.assertEqual(before, snapshot(self.ws))

    def test_git_worktree_file_is_accepted(self) -> None:
        marker = self.src / "kanata_common" / ".git"
        shutil.rmtree(marker)
        marker.write_text("gitdir: /example/worktree-metadata\n")
        before = snapshot(self.ws)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("WARNING:", result.stdout)
        self.assertEqual(before, snapshot(self.ws))

    def test_invalid_repository_list_aborts_without_writes(self) -> None:
        invalid_documents = (
            None,
            [],
            {"repositories": {}},
            {"repositories": [None]},
            {"repositories": [{"name": "../escape", "path": "src/../escape"}]},
            {"repositories": [{"name": "kanata_common", "path": "/tmp/outside"}]},
            {"repositories": [{"name": "kanata_common", "path": "src/../outside"}]},
            {"repositories": [{"name": "kanata_common", "path": "src/kanata_common"}] * 2},
        )
        config = self.workflow / "config" / "repositories.json"
        for document in invalid_documents:
            with self.subTest(document=document):
                config.write_text(json.dumps(document))
                before = snapshot(self.ws)
                result = self.run_setup("--apply")
                self.assertEqual(result.returncode, 1)
                self.assertIn("repository candidate list", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(before, snapshot(self.ws))

    def test_missing_repository_list_aborts_without_writes(self) -> None:
        (self.workflow / "config" / "repositories.json").unlink()
        before = snapshot(self.ws)
        result = self.run_setup("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("repository candidate list", result.stderr)
        self.assertEqual(before, snapshot(self.ws))

    def test_malformed_json_aborts_without_writes(self) -> None:
        (self.workflow / "config" / "repositories.json").write_text("{invalid JSON}")
        before = snapshot(self.ws)
        result = self.run_setup("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("repository candidate list", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(before, snapshot(self.ws))

    def test_apply_installs_relative_entrypoints_and_preserves_src(self) -> None:
        before = snapshot(self.src)
        result = self.run_setup("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, snapshot(self.src))
        links = [self.ws / "AGENTS.md", *sorted((self.ws / ".agents" / "skills").iterdir())]
        self.assertEqual(
            {link.name for link in links},
            {
                "AGENTS.md",
                "kanata-refactor",
                "kanata-commit",
                "kanata-fix",
                "kanata-feat",
                "kanata-audit",
                "kanata-review",
                "kanata-error-review",
            },
        )
        self.assertEqual(
            (self.ws / ".agents" / "skills" / "kanata-review").resolve(),
            self.workflow / "skills" / "kanata-review",
        )
        for link in links:
            self.assertTrue(link.is_symlink())
            self.assertTrue(link.exists())
            self.assertFalse(os.path.isabs(os.readlink(link)))
        self.assertEqual(
            (self.ws / "AGENTS.md").read_bytes(), (self.workflow / "AGENTS.md").read_bytes()
        )
        self.assertFalse((self.ws / ".git").exists())
        self.assertFalse((self.ws / ".codex").exists())

    def test_repeated_apply_is_idempotent(self) -> None:
        self.assertEqual(self.run_setup("--apply").returncode, 0)
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--apply").returncode, 0)
        self.assertEqual(before, snapshot(self.ws))

    def test_apply_adds_review_to_existing_installation(self) -> None:
        for name in ("kanata-review", "kanata-error-review"):
            with self.subTest(skill=name):
                self.assertEqual(self.run_setup("--apply").returncode, 0)
                review = self.ws / ".agents" / "skills" / name
                review.unlink()
                before = snapshot(self.ws)
                result = self.run_setup("--apply")
                self.assertEqual(result.returncode, 0, result.stderr)
                after = snapshot(self.ws)
                self.assertEqual(set(after) - set(before), {f".agents/skills/{name}"})
                for key, value in before.items():
                    self.assertEqual(after.get(key), value, key)
                self.assertEqual(review.resolve(), self.workflow / "skills" / name)

    def test_check_passes_after_install_without_writes(self) -> None:
        self.assertEqual(self.run_setup("--apply").returncode, 0)
        before = snapshot(self.ws)
        result = self.run_setup("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, snapshot(self.ws))

    def test_check_missing_fails_without_writes(self) -> None:
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--check").returncode, 1)
        self.assertEqual(before, snapshot(self.ws))

    def test_existing_agents_file_is_preserved(self) -> None:
        (self.ws / "AGENTS.md").write_text("Existing team instructions\n")
        before = snapshot(self.ws)
        result = self.run_setup("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("will not overwrite", result.stderr)
        self.assertEqual(before, snapshot(self.ws))

    def test_existing_skill_aborts_before_any_install(self) -> None:
        skill = self.ws / ".agents" / "skills" / "kanata-audit"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("Existing skill\n")
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--apply").returncode, 1)
        self.assertEqual(before, snapshot(self.ws))
        self.assertFalse((self.ws / "AGENTS.md").exists())

    def test_agents_override_blocks_install(self) -> None:
        (self.ws / "AGENTS.override.md").write_text("Override\n")
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--apply").returncode, 1)
        self.assertEqual(before, snapshot(self.ws))

    def test_symlink_agents_parent_blocks_install(self) -> None:
        external = self.base / "external agents"
        external.mkdir()
        (self.ws / ".agents").symlink_to(external, target_is_directory=True)
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--apply").returncode, 1)
        self.assertEqual(before, snapshot(self.ws))
        self.assertEqual(list(external.iterdir()), [])

    def test_symlink_skills_parent_blocks_install(self) -> None:
        (self.ws / ".agents").mkdir()
        external = self.base / "external skills"
        external.mkdir()
        (self.ws / ".agents" / "skills").symlink_to(external, target_is_directory=True)
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--apply").returncode, 1)
        self.assertEqual(before, snapshot(self.ws))
        self.assertEqual(list(external.iterdir()), [])

    def test_dangling_agents_link_is_not_overwritten(self) -> None:
        (self.ws / "AGENTS.md").symlink_to("missing.md")
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--apply").returncode, 1)
        self.assertEqual(before, snapshot(self.ws))

    def test_workflow_can_reside_outside_workspace(self) -> None:
        outside = self.base / "shared workflow"
        shutil.move(self.workflow, outside)
        self.workflow = outside
        result = self.run_setup("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.ws / "AGENTS.md").resolve(), self.workflow / "AGENTS.md")
        self.assertEqual(self.run_setup("--check").returncode, 0)

    def test_missing_src_does_not_create_workspace_scaffold(self) -> None:
        shutil.rmtree(self.src)
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--apply").returncode, 1)
        self.assertEqual(before, snapshot(self.ws))

    def test_missing_skill_source_aborts_before_writes(self) -> None:
        (self.workflow / "skills" / "kanata-feat" / "SKILL.md").unlink()
        before = snapshot(self.ws)
        self.assertEqual(self.run_setup("--apply").returncode, 1)
        self.assertEqual(before, snapshot(self.ws))

    def test_generic_skills_are_not_deleted(self) -> None:
        existing = self.ws / ".agents" / "skills" / "issue"
        existing.mkdir(parents=True)
        (existing / "SKILL.md").write_text("Legacy skill\n")
        before = snapshot(existing)
        result = self.run_setup("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("legacy Skill 'issue'", result.stdout)
        self.assertEqual(before, snapshot(existing))

    def test_apply_rolls_back_only_its_new_entries(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "kanata_setup_test_module", SOURCE / "scripts" / "setup.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        plans = module.prepare_plan(self.ws, self.workflow)
        before = snapshot(self.ws)
        original = Path.symlink_to
        count = 0

        def fail_second(path, *args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("Injected failure")
            return original(path, *args, **kwargs)

        with patch.object(Path, "symlink_to", fail_second):
            with self.assertRaises(OSError):
                module.apply_plan(plans, self.ws)
        self.assertEqual(before, snapshot(self.ws))


if __name__ == "__main__":
    unittest.main()
