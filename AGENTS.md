# KANATA coding workflow

このファイルは、KANATAのローカル開発でAIが読む入口である。
人とAIが共有する開発規約は`rules/`、作業別の手順は`skills/`に置く。
ユーザーとの会話・作業報告は日本語、コミットメッセージは英語にする。

## 資料の役割

| 資料 | 内容 |
| --- | --- |
| `rules/common.md`・`rules/kanata.md` | 作業の進め方、配置、対象とROS 2の前提 |
| `rules/coding.md` | 人とAIに共通するコーディング規約 |
| `rules/git.md` | ブランチ・コミットの規約とAIによるGit操作の境界 |
| `rules/testing.md` | 検証方法、結果の記録、作業別の実行範囲 |
| `rules/review.md` | 変更のレビューで確認する観点と、指摘のまとめ方 |
| `rules/communication.md` | 会話・Issue・PRの説明方法、図とスクリーンショットの使い方 |
| `skills/` | AI向けの作業別手順とCodex用の設定 |
| `config/repositories.json` | ROS 2の対象リポジトリの候補一覧 |
| `SOURCES.md` | 参考資料とKANATA独自の方針 |

## 入口と参照資料

- 通常の開始ディレクトリは既存のKANATAワークスペース（例: `~/kanata_ws`）。
- ワークスペースを新たにGit管理しない。実装は既存の`src/`配下の独立リポジトリにある。
- このAGENTS.mdの実体があるディレクトリを`WORKFLOW_ROOT`とする。
  ワークスペースの`AGENTS.md`は通常、実体へのシンボリックリンクである。
  相対参照は現在の作業ディレクトリではなく、実体の`WORKFLOW_ROOT`を基準に解決する。
- 最初に`WORKFLOW_ROOT/rules/common.md`、`rules/kanata.md`、`rules/communication.md`を読む。
- コード編集・調査では`rules/coding.md`、検証では`rules/testing.md`、
  Gitの書き込み操作では`rules/git.md`を読む。差分やPRのレビューでは`rules/review.md`も読む。
- 対象の候補一覧は`config/repositories.json`を読む。このJSONはAIツールの標準設定ではなく、
  このワークフローが参照する独自の案内資料である。
- 一覧の全リポジトリが各PCにあるとは仮定しない。PCごとの配置と未配置の扱いは`rules/kanata.md`に従う。
  `kanata_workflow`自体への明示的な作業依頼も扱えるが、`src/`への移動やROSパッケージ化はしない。
- 対象リポジトリと編集するディレクトリにある既存のAGENTS.md / AGENTS.override.md、
  pre-commit、formatter、lint設定を読む。子リポジトリの指示が自動注入されたと仮定しない。
- 明示的なユーザー指示をこのワークフローの既定方針より優先する。
  指示の優先順位・不明点の扱いは`rules/common.md`に従う。

## 全作業に共通する注意

以下は重要事項の要約であり、詳細は参照先の規約に従う。

- 指定範囲で作業し、元からある変更を守る。実機操作や秘密情報の扱いも`rules/common.md`に従う。
- 明示依頼のないコミット・push・GitHubへの投稿や変更は行わない。
  ブランチ・ステージ操作を含む許可範囲は`rules/git.md`に従う。
- 検査は`rules/testing.md`に従って選び、実施済みと未確認を分けて報告する。

## 作業メニュー

| Skill | 目的 | 変更できる範囲 |
| --- | --- | --- |
| `kanata-refactor` | 命名・規約・整形・可読性の整理 | 挙動を変えない指定範囲だけ |
| `kanata-commit` | 既存差分を意味ごとにコミット | 許可されたGit操作。コード修正は別作業 |
| `kanata-fix` | 不具合修正 | 一度に一つの原因・Issueと必要なテスト |
| `kanata-feat` | 指定機能の実装 | 依頼された機能と必要なテスト |
| `kanata-audit` | 改善候補の調査 | 原則読み取りのみ。修正・Issue登録なし |
| `kanata-review` | 指定された差分・PRのレビュー | 読み取りと会話での報告のみ。修正・GitHubへの投稿なし |

通常の自然文による依頼も、この入口と`rules/`に従って作業できる。
会話中の例示・引用や方法の質問は実行依頼と区別する。
「Issueを立てる」はGitHubへの登録依頼であり、`kanata-audit`による調査とは区別する。

### Codex固有の設定と呼び出し

Skillは`$kanata-refactor`などの名前、またはUIで明示的に選択する。
選択されたSkillの`WORKFLOW_ROOT/skills/<skill-name>/SKILL.md`を読み、その手順で実行する。
6つのSkillは`agents/openai.yaml`で`allow_implicit_invocation: false`とし、暗黙の選択を無効にする。
他のAIを使う場合は、規約・手順の読み込ませ方を確認する。Codex用の設定・呼び出しが使えるとは仮定しない。

## 適用範囲

この入口はローカル開発用である。GitHubの自動レビューへの規約配布、
複数段階の自動レビュー、24時間稼働の仕組みは含まない。
別リポジトリを単独で開いた場合の読み込みや、別セッションでのSkill検出は実際に確認する。

## 終了時

`rules/common.md`の終了報告の項目を、`rules/communication.md`の書き方で簡潔に伝える。
