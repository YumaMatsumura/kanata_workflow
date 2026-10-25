#!/usr/bin/env python3
"""Distribute committed KANATA review rules without network access or Git writes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote
from urllib.parse import unquote
from urllib.parse import urlsplit

SOURCE_URL = "https://github.com/YumaMatsumura/kanata_workflow"
BUNDLE = ".github/kanata/review"
MANIFEST = f"{BUNDLE}/SOURCE.json"
SECTIONS = {
    "rules/review.md": None,
    "rules/coding.md": None,
    "rules/common.md": (
        "変更を必要最小限にする",
        "既存の変更を守る",
        "コマンドや実機を扱うとき",
    ),
    "rules/kanata.md": ("ROS 2と実行環境", "既存の名前と動作を守る"),
    "rules/testing.md": (
        "何を確認するか",
        "CIとローカルの使い分け",
        "ビルド・テストと結果の記録",
    ),
    "rules/communication.md": (
        "説明する順番",
        "日本語の書き方",
        "図とスクリーンショット",
        "確認結果の書き方",
    ),
    "SOURCES.md": None,
}
LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^\s)]+)\)")


class DistributionError(Exception):
    """The requested distribution cannot be performed safely."""


def git(root, *args):
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise DistributionError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def select_sections(content, headings):
    if headings is None:
        return content
    # Canonical documents use level-two headings outside fenced code.
    parts = re.split(r"(?m)(?=^## )", content)
    selected = [content.splitlines()[0] + "\n\n"]
    for heading in headings:
        matches = [part for part in parts[1:] if part.splitlines()[0] == f"## {heading}"]
        if len(matches) != 1:
            raise DistributionError(f"規約の節を一意に取得できません: {heading}")
        selected.append(matches[0].rstrip() + "\n\n")
    return "".join(selected).rstrip() + "\n"


def rewrite_links(content, source_path, commit):
    def replace(match):
        label, destination = match.groups()
        url = urlsplit(destination)
        if url.scheme or url.netloc or not url.path:
            return match.group(0)
        resolved = posixpath.normpath(
            posixpath.join(posixpath.dirname(source_path), unquote(url.path))
        )
        if resolved in SECTIONS or resolved == "rules":
            return match.group(0)
        # Optional background stays at the same source version, never a moving main branch.
        pinned = f"{SOURCE_URL}/blob/{commit}/{quote(resolved, safe='/')}"
        if url.fragment:
            pinned += "#" + url.fragment
        return f"[{label}]({pinned})"

    lines = []
    fence = None
    for line in content.splitlines(keepends=True):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append(line)
        else:
            lines.append(LINK.sub(replace, line) if fence is None else line)
    return "".join(lines)


def entrypoint():
    return f"""# KANATA repository guidance

このファイルと`{BUNDLE}/`は、`kanata_workflow`から生成したレビュー用の入口と規約です。
原本の版は[SOURCE.json]({MANIFEST})に記録しています。生成物を手作業で編集せず、配布ツールで更新します。

以下は差分・PRのレビューに適用します。通常の実装作業では、ユーザーの依頼と適用されるワークスペースの指示に従います。

## Code Review Rules

- レビューを始めるときは、[レビュー基準]({BUNDLE}/rules/review.md)と[説明方法]({BUNDLE}/rules/communication.md)を読みます。
- 変更範囲と既存動作は[共通方針]({BUNDLE}/rules/common.md)、ROS 2の前提は[KANATAの規約]({BUNDLE}/rules/kanata.md)で確認します。
- コード・launch・設定・テストの変更では、関係する[コーディング規約]({BUNDLE}/rules/coding.md)を確認します。
  検証内容とCI結果は[検証の規約]({BUNDLE}/rules/testing.md)に従って判断します。
- レビューの依頼だけでコード修正や実機操作まで許可されたとは扱いません。
  必要な資料・依存先・検証結果が確認できない場合は、推測で補わず未確認として伝えます。
""".encode()


def build_bundle(source, source_ref):
    commit = git(source, "rev-parse", "--verify", "--end-of-options", f"{source_ref}^{{commit}}")
    commit = commit.decode().strip()
    files = {"AGENTS.md": entrypoint()}
    sources = {}
    for path, headings in SECTIONS.items():
        raw = git(source, "show", f"{commit}:{path}")
        content = select_sections(raw.decode("utf-8"), headings)
        content = rewrite_links(content, path, commit)
        title, body = content.split("\n", 1)
        header = "\n<!-- Generated from kanata_workflow; edit the source, then redistribute. -->\n"
        files[f"{BUNDLE}/{path}"] = (title + "\n" + header + body).encode()
        sources[path] = {"sha256": digest(raw), "sections": headings}
    files[MANIFEST] = json_bytes(
        {
            "format_version": 1,
            "source_repository": SOURCE_URL,
            "source_commit": commit,
            "source_files": sources,
            "generator_sha256": digest(Path(__file__).read_bytes()),
            "generated_files": {path: digest(data) for path, data in files.items()},
        }
    )
    return files


def validate_target(target, source, files):
    if not target.is_dir():
        raise DistributionError(f"対象リポジトリがありません: {target}")
    if (
        target == source
        or Path(git(target, "rev-parse", "--show-toplevel").decode().strip()) != target
    ):
        raise DistributionError(
            "配布先にはkanata_workflow以外のGitリポジトリのルートを指定します。"
        )
    if os.path.lexists(target / "AGENTS.override.md"):
        raise DistributionError(
            "AGENTS.override.mdがあります。指示の優先関係を先に確認してください。"
        )
    for name in files:
        current = target
        for part in Path(name).parts:
            current /= part
            if current.is_symlink():
                raise DistributionError(f"配布先にシンボリックリンクがあります: {current}")
            if current.exists() and current != target / name and not current.is_dir():
                raise DistributionError(f"配布先の親がディレクトリではありません: {current}")
        if current.exists() and not current.is_file():
            raise DistributionError(f"配布先が通常ファイルではありません: {current}")


def plan_changes(target, files):
    previous = None
    manifest_path = target / MANIFEST
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text())
            hashes = previous["generated_files"]
            valid = (
                previous["format_version"] == 1
                and previous["source_repository"] == SOURCE_URL
                and set(hashes) == set(files) - {MANIFEST}
                and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values())
            )
        except (ValueError, KeyError, TypeError):
            valid = False
        if not valid:
            raise DistributionError("SOURCE.jsonが不正です。自動では上書きしません。")
    changes = {}
    for name, expected in files.items():
        path = target / name
        actual = path.read_bytes() if path.exists() else None
        if actual == expected:
            continue
        if actual is not None and name != MANIFEST:
            if previous is None or digest(actual) != previous["generated_files"][name]:
                raise DistributionError(f"既存ファイルと衝突、または生成後の編集があります: {path}")
        changes[name] = (actual, expected)
    return changes


def atomic_write(path, data):
    descriptor, temporary = tempfile.mkstemp(prefix=".kanata-review-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_changes(target, changes):
    created_dirs = []
    written = []
    try:
        for name, (before, after) in changes.items():
            path = target / name
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                created_dirs.append(directory)
            current = path.read_bytes() if path.exists() else None
            if current != before:
                raise DistributionError(f"計画後に配布先が変更されました: {path}")
            atomic_write(path, after)
            written.append((path, before))
    except Exception:
        for path, before in reversed(written):
            if before is None:
                path.unlink()
            else:
                atomic_write(path, before)
        for directory in reversed(created_dirs):
            directory.rmdir()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True, help="配布先Gitリポジトリのルート")
    parser.add_argument("--source-ref", default="HEAD", help="原本のコミット・タグ（既定: HEAD）")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true", help="生成物を書き込む")
    modes.add_argument("--check", action="store_true", help="一致を検査する。書き込まない")
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parent.parent
    target = args.target.expanduser().resolve()
    try:
        files = build_bundle(source, args.source_ref)
        validate_target(target, source, files)
        changes = plan_changes(target, files)
        print(f"Source: {json.loads(files[MANIFEST])['source_commit']}")
        print(f"Target: {target}")
        for name, (before, _) in changes.items():
            print(f"[{'CREATE' if before is None else 'UPDATE'}] {name}")
        if args.check:
            print(
                "[DIFF] 配布が必要です。" if changes else "[OK] 生成物は指定した原本と一致します。"
            )
            return int(bool(changes))
        if args.apply:
            apply_changes(target, changes)
            print(f"APPLIED: {len(changes)} file(s)")
        else:
            print("DRY RUN: 書き込みません。反映には--applyを指定してください。")
        return 0
    except (DistributionError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
