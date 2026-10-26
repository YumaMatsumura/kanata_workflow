#!/usr/bin/env python3
"""Print rule provenance and content hashes as JSON without writing files or Git."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

FILES = (
    "AGENTS.md",
    "rules/common.md",
    "rules/kanata.md",
    "rules/communication.md",
    "rules/review.md",
    "rules/error-review.md",
    "rules/coding.md",
    "rules/testing.md",
    "skills/kanata-error-review/SKILL.md",
    "skills/kanata-error-review/scripts/collect_rule_context.py",
)


def git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect(root: Path) -> dict:
    root = root.resolve()
    warnings = []
    commit = None
    status = None
    top = git(root, "rev-parse", "--show-toplevel")
    if top is not None and top.returncode == 0:
        git_root = Path(top.stdout.decode("utf-8", errors="replace").strip()).resolve()
        if git_root == root:
            head = git(root, "rev-parse", "--verify", "HEAD")
            if head is not None and head.returncode == 0:
                commit = head.stdout.decode("ascii").strip()
                result = git(
                    root, "status", "--porcelain=v1", "--untracked-files=all", "--", *FILES
                )
                if result is not None and result.returncode == 0:
                    status = result.stdout.decode("utf-8", errors="replace").splitlines()
                else:
                    warnings.append("関連ファイルのGit状態を取得できません。")
    if commit is None:
        warnings.append("参照元自身のGitコミットを確認できません。親リポジトリの版は代用しません。")

    files = {}
    for name in FILES:
        path = root / name
        entry = {"sha256": None, "head_sha256": None, "state": "unversioned"}
        try:
            entry["sha256"] = digest(path.read_bytes())
        except OSError:
            entry["state"] = "unreadable"
            warnings.append(f"規約・手順を読み取れません: {name}")
        if commit is not None:
            tree = git(root, "ls-tree", "-z", commit, "--", name)
            if tree is None or tree.returncode:
                warnings.append(f"原本コミット内のファイルを確認できません: {name}")
                if entry["sha256"] is not None:
                    entry["state"] = "unverified"
            elif not tree.stdout:
                if entry["sha256"] is not None:
                    entry["state"] = "not_in_head"
            else:
                original = git(root, "show", f"{commit}:{name}")
                if original is None or original.returncode:
                    warnings.append(f"原本ファイルの内容を取得できません: {name}")
                    if entry["sha256"] is not None:
                        entry["state"] = "unverified"
                else:
                    entry["head_sha256"] = digest(original.stdout)
                    if entry["sha256"] is not None:
                        entry["state"] = (
                            "clean" if entry["sha256"] == entry["head_sha256"] else "modified"
                        )
        files[name] = entry

    known = commit is not None and status is not None
    known = known and all(entry["state"] != "unverified" for entry in files.values())
    return {
        "format_version": 1,
        "source_root": str(root),
        "source_commit": commit,
        "has_local_changes": (
            bool(status or any(entry["state"] != "clean" for entry in files.values()))
            if known
            else None
        ),
        "git_status": status,
        "files": files,
        "collector_sha256": digest(Path(__file__).read_bytes()),
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    context = collect(args.workflow_root.expanduser())
    print(json.dumps(context, ensure_ascii=False, indent=2))
    return int(any(entry["sha256"] is None for entry in context["files"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
