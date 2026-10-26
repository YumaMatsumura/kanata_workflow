#!/usr/bin/env python3
"""Prepare review-rule sync files and PR text; never contact GitHub or write Git state."""

import argparse
import json
from pathlib import Path
import re
import sys

import sync_review_rules as sync

TARGET_NAMES = ("kanata_common", "kanata_core", "kanata_operation")


def source_commit(source, revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise sync.DistributionError("配布元は完全なコミットIDで指定してください。")
    return sync.git(source, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()


def sync_matrix(source, commit):
    config = json.loads(sync.git(source, "show", f"{commit}:config/repositories.json"))
    if config.get("development_branch") != "main":
        raise sync.DistributionError("自動同期の取り込み先はmainです。設定を確認してください。")
    repositories = config.get("repositories", [])
    targets = []
    for name in TARGET_NAMES:
        matches = [item for item in repositories if item.get("name") == name]
        if len(matches) != 1:
            raise sync.DistributionError(f"同期先を一意に取得できません: {name}")
        repository = matches[0].get("github_repository", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/" + name, repository):
            raise sync.DistributionError(f"GitHubリポジトリ名が不正です: {name}")
        targets.append({"repository": repository, "name": name})
    return {"include": targets}


def pr_body(commit, previous_commit):
    previous = (
        f"[{previous_commit[:7]}]({sync.SOURCE_URL}/commit/{previous_commit})"
        if previous_commit
        else "未導入"
    )
    return f"""## 概要

KANATAの共通レビュー規約を、`kanata_workflow`のコミット`{commit[:7]}`にそろえます。
規約の原本は`kanata_workflow`で管理し、このリポジトリにはレビューで読むコピーを配置します。

作成・変更の担当：GitHub Actionsによる自動同期。AIによるレビューは実行していません。

## 関連Issue

なし（共通規約の同期PR）

## 変更内容・影響範囲

- 取得元：{previous} → [{commit[:7]}]({sync.SOURCE_URL}/commit/{commit})
- 対象は`AGENTS.md`と`.github/kanata/review/`内の生成ファイルだけです。
- `SOURCE.json`に、原本のコミットID・取り込んだ節・照合用ハッシュ値を記録します。
- 規約の差分は、PRの変更ファイルで確認してください。パッケージ本体・launch・CI設定は変更しません。

## 確認結果

確認環境：GitHub Actions、Ubuntu 24.04・Python 3.12。規約の生成と照合は同期ツールが実施しました。

| 確認項目 | 結果 | 実行内容・根拠／未実施理由 |
| --- | --- | --- |
| lint・整形 | 未実施 | 同期先リポジトリの、このPRに対するCI結果を確認してください。 |
| ビルド | 対象外 | レビュー規約と取得元の記録だけの変更です。 |
| 自動テスト | 成功（配布元） | 同期処理に先立ち、配布元の`test_review_rules.py`と`test_review_rules_pr.py`を実行しました。テスト件数と結果は配布元のActionsログで確認できます。同期先の検査とは別です。 |
| 動作確認 | 成功（ファイル配置） | 配布後の全生成物を、指定したコミットの原本から作成した内容と照合しました。AIが実際に規約を使ったかの確認は未実施です。 |

配布元の実行履歴：[sync-review-rules]({sync.SOURCE_URL}/actions/workflows/sync-review-rules.yaml)

## 未確認事項・判断してほしい点

規約の変更内容と、このPRのCI結果をご確認ください。マージは人が行います。
このブランチは自動同期専用です。生成ファイルは手で編集せず、原本の`kanata_workflow`を修正してください。
"""


def prepare(source, target, revision, body_file, apply):
    commit = source_commit(source, revision)
    files = sync.build_bundle(source, commit)
    sync.validate_target(target, source, files)
    if sync.git(target, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise sync.DistributionError("自動同期用の配布先には、変更のないチェックアウトを使います。")
    if (
        body_file == target
        or target in body_file.parents
        or body_file == source
        or source in body_file.parents
    ):
        raise sync.DistributionError("PR本文は、配布元・配布先リポジトリの外へ出力してください。")
    previous = None
    manifest_path = target / sync.MANIFEST
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_bytes())["source_commit"]
        except (ValueError, KeyError, TypeError):
            raise sync.DistributionError("既存のSOURCE.jsonが不正です。") from None
        if not isinstance(previous, str) or not re.fullmatch(r"[0-9a-f]{40}", previous):
            raise sync.DistributionError("既存の配布元コミットIDが不正です。")
    changes = sync.plan_changes(target, files)
    if apply:
        # Prepare the text first so a bad output path cannot leave a partial distribution.
        body_file.parent.mkdir(exist_ok=True, parents=True)
        sync.atomic_write(body_file, pr_body(commit, previous).encode())
        sync.apply_changes(target, changes)
        if sync.plan_changes(target, files):
            raise sync.DistributionError("配布後の生成物が原本と一致しません。")
    return {
        "source_sha": commit,
        "changed": str(bool(changes)).lower(),
        "add_paths": "\n".join(files),
    }


def write_outputs(path, values):
    if not path:
        return
    with path.open("a", encoding="utf-8") as stream:
        for name, value in values.items():
            # Names and values come from the validated matrix and generated path list.
            stream.write(f"{name}<<KANATA_OUTPUT\n{value}\nKANATA_OUTPUT\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", action="store_true", help="同期先の行列と配布元コミットを出力")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--source-ref", help="配布元の完全なコミットID")
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--github-output", type=Path, help="Actionsのステップ出力先")
    parser.add_argument("--apply", action="store_true", help="生成ファイルとPR本文を書き込む")
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parent.parent
    try:
        if args.matrix:
            if args.target or args.body_file or args.source_ref or args.apply:
                parser.error("--matrixは配布用の引数と同時に指定できません。")
            commit = sync.git(source, "rev-parse", "HEAD").decode().strip()
            matrix = sync_matrix(source, commit)
            values = {"source_sha": commit, "matrix": json.dumps(matrix)}
            print(json.dumps(matrix))
        else:
            if not (args.target and args.source_ref and args.body_file):
                parser.error("--target、--source-ref、--body-fileが必要です。")
            values = prepare(
                source,
                args.target.expanduser().resolve(),
                args.source_ref,
                args.body_file.expanduser().resolve(),
                args.apply,
            )
            print(f"{'APPLIED' if args.apply else 'DRY RUN'}: changed={values['changed']}")
        write_outputs(args.github_output, values)
        return 0
    except (sync.DistributionError, OSError, ValueError, TypeError, AttributeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
