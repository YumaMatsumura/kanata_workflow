#!/usr/bin/env python3
"""Install KANATA workspace entrypoints without overwriting existing files.

Python 3.10+, standard library only. The default action is a read-only plan.
Only --apply creates links/directories. Source repos and Git are not changed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys

SKILL_NAMES = (
    "kanata-refactor",
    "kanata-commit",
    "kanata-fix",
    "kanata-feat",
    "kanata-audit",
    "kanata-review",
)
LEGACY_NAMES = ("refactor", "commit", "fix", "feat", "issue", "docs")


class SetupError(Exception):
    """A conflict that must not be resolved automatically."""


@dataclass(frozen=True)
class LinkPlan:
    destination: Path
    target: Path
    already_installed: bool


def lexists(path: Path) -> bool:
    """Unlike Path.exists(), include dangling symlinks."""
    return os.path.lexists(path)


def require_real_directory_or_absent(path: Path) -> None:
    if lexists(path) and (path.is_symlink() or not path.is_dir()):
        raise SetupError(f"Existing path must be a real directory: {path}")


def prepare_plan(workspace: Path, workflow: Path) -> list[LinkPlan]:
    """Validate all destinations before making any changes."""
    if not workspace.is_dir():
        raise SetupError(f"Workspace does not exist: {workspace}")
    if not (workspace / "src").is_dir():
        raise SetupError(f"Existing src/ directory not found: {workspace / 'src'}")
    if workspace == workflow:
        raise SetupError("Workspace and workflow repository must be different directories.")
    if lexists(workspace / "AGENTS.override.md"):
        raise SetupError(
            f"AGENTS.override.md would take precedence: {workspace / 'AGENTS.override.md'}\n"
            "Review and integrate existing instructions manually; nothing was changed."
        )
    for directory in (workspace / ".agents", workspace / ".agents" / "skills"):
        require_real_directory_or_absent(directory)
    pairs = [(workspace / "AGENTS.md", workflow / "AGENTS.md")]
    pairs.extend(
        (workspace / ".agents" / "skills" / name, workflow / "skills" / name)
        for name in SKILL_NAMES
    )
    plans: list[LinkPlan] = []
    for destination, target in pairs:
        required = target / "SKILL.md" if target.name in SKILL_NAMES else target
        if not required.is_file():
            raise SetupError(f"Workflow source is missing or invalid: {required}")
        installed = False
        if lexists(destination):
            installed = destination.is_symlink() and destination.resolve() == target.resolve()
            if not installed:
                raise SetupError(
                    f"Conflicting entry (will not overwrite): {destination}\n"
                    "Review existing content; this setup has no --force option."
                )
        plans.append(LinkPlan(destination, target.resolve(), installed))
    return plans


def apply_plan(plans: list[LinkPlan], workspace: Path) -> None:
    """Create absent entries; undo only our own changes after a failure."""
    created_dirs: list[Path] = []
    created_links: list[tuple[Path, str]] = []
    try:
        for directory in (workspace / ".agents", workspace / ".agents" / "skills"):
            require_real_directory_or_absent(directory)
            if not lexists(directory):
                directory.mkdir()
                created_dirs.append(directory)
        if lexists(workspace / "AGENTS.override.md"):
            raise SetupError("AGENTS.override.md appeared after planning; installation stopped.")
        for item in plans:
            if item.already_installed:
                if not item.destination.is_symlink() or item.destination.resolve() != item.target:
                    raise SetupError(f"Entry changed after planning: {item.destination}")
                continue
            relative_target = os.path.relpath(item.target, item.destination.parent)
            # symlink() fails on any concurrent entry. Never overwrite/replace it.
            item.destination.symlink_to(relative_target, target_is_directory=item.target.is_dir())
            created_links.append((item.destination, relative_target))
    except Exception:
        for destination, value in reversed(created_links):
            try:
                if destination.is_symlink() and os.readlink(destination) == value:
                    destination.unlink()
            except OSError as error:
                print(f"WARNING: could not undo our link {destination}: {error}", file=sys.stderr)
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()  # Only empty directories can be removed.
            except OSError:
                pass
        raise


def load_repository_paths(workflow: Path) -> list[Path]:
    """Read optional candidates; none of them is required by this installer."""
    config_path = workflow / "config" / "repositories.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        entries = data["repositories"]
        if not isinstance(entries, list):
            raise ValueError("repositories must be a list")
        paths: list[Path] = []
        for entry in entries:
            name = entry["name"]
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                raise ValueError("invalid repository name")
            if entry["path"] != f"src/{name}":
                raise ValueError("repository paths must be src/<name>")
            relative_path = Path(entry["path"])
            if relative_path in paths:
                raise ValueError("duplicate repository path")
            paths.append(relative_path)
        return paths
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        raise SetupError(
            f"Invalid or missing repository candidate list: {config_path}\n"
            "Expected a repositories list with unique names and src/<name> paths."
        ) from None


def show_repository_status(workspace: Path, repository_paths: list[Path]) -> None:
    for relative_path in repository_paths:
        path = workspace / relative_path
        if not lexists(path):
            print(f"[NOT PLACED] {path} (optional)")
        elif not path.is_dir():
            print(f"WARNING: expected a repository directory: {path}")
        elif not lexists(path / ".git"):
            print(f"WARNING: no .git entry at listed repository root: {path}")
        else:
            print(f"[PRESENT] {path}")
    for name in LEGACY_NAMES:
        if lexists(workspace / ".agents" / "skills" / name):
            print(f"WARNING: existing generic/legacy Skill '{name}' was left unchanged.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", type=Path, required=True, help="Existing KANATA workspace, e.g. ~/kanata_ws"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true", help="Create missing entrypoints")
    modes.add_argument(
        "--check", action="store_true", help="Read-only check; missing entries exit 1"
    )
    args = parser.parse_args(argv)
    workflow = Path(__file__).resolve().parents[1]
    try:
        workspace = args.workspace.expanduser().resolve(strict=True)
        repository_paths = load_repository_paths(workflow)
        plans = prepare_plan(workspace, workflow)
        mode = "APPLY" if args.apply else "CHECK" if args.check else "PLAN (no writes)"
        print(f"{mode}\nWorkspace: {workspace}\nWorkflow:  {workflow}")
        for item in plans:
            state = "OK" if item.already_installed else "MISSING" if args.check else "CREATE"
            print(f"[{state}] {item.destination} -> {item.target}")
        show_repository_status(workspace, repository_paths)
        if args.check:
            missing = sum(not p.already_installed for p in plans)
            if missing:
                print(f"{missing} entrypoint(s) missing. Nothing was changed.")
                return 1
            print("Filesystem entrypoints verified. Verify actual loading in a new Codex session.")
            return 0
        if args.apply:
            apply_plan(plans, workspace)
            print(
                "Entrypoints installed. Existing repositories and Codex settings were not changed."
            )
        else:
            print("Review the plan, then run again with --apply. Nothing was changed.")
        return 0
    except (SetupError, OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
