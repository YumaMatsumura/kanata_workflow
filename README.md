# kanata_workflow

四脚ロボットKANATAの開発規約、作業手順、開発支援ツールを管理するリポジトリです。

人とAIが共通の基準で開発・レビューを進めるための情報をまとめます。

## 読む資料

「主な読み手」を示しています。AI向け資料も、人が作業手順を確認・見直す際に参照できます。

| 主な読み手 | 資料 | 内容 |
| --- | --- | --- |
| 人 | [BOOTSTRAP_PROMPT.md](BOOTSTRAP_PROMPT.md) | AI導入時の設定確認に使う依頼文。普段の作業では不要 |
| 人 | [scripts/README.md](scripts/README.md) | ローカル開発環境への導入手順と確認方法 |
| 人、AI | [rules/](rules/) | 開発時に守る規約、Gitの使い方、変更の確認方法、説明の書き方 |
| 人、AI | [SOURCES.md](SOURCES.md) | 規約の参考資料と、参考にした内容 |
| AI | [AGENTS.md](AGENTS.md) | 作業開始時の入口と参照先 |
| AI | [skills/](skills/) | 調査・実装・修正・コミット等の作業別手順 |

開発規約は、まず[rules/common.md](rules/common.md)を読み、作業に応じて各規約を参照してください。
プロジェクト全体の設計・操作・開発ガイドの管理先は`kanata_docs`です。
`config/`・`scripts/`・`tools/`は、設定と開発支援ツールを置く場所です。
