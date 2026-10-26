# 各リポジトリへレビュー規約を配布する

`sync_review_rules.py`で、`kanata_workflow`の共通規約とレビュー用の`AGENTS.md`を対象リポジトリへ配置します。
GitHub上でも、そのリポジトリだけでKANATAのレビュー基準を読めるようにするためです。

## 原本とコピーの役割

規約の原本は`kanata_workflow/rules/`です。変更するときは原本を編集します。
各リポジトリには、原本の特定のコミットから生成した通常のファイルを置き、Gitで管理します。
配布先のファイルは、手作業で編集しません。

ローカル開発用の[setup.py](README.md)は、ワークスペースにリンクを作る別の仕組みです。
今回の配布では、隣に`kanata_workflow`があることや、ネットワークで規約を取得できることを前提にしません。

| 配布先（対象リポジトリ基準） | 内容 |
| --- | --- |
| `AGENTS.md` | レビュー時に読む規約への短い入口 |
| `.github/kanata/review/rules/` | コーディング・レビュー基準の全文と、共通方針・ROS 2の前提・検証・説明方法の必要な節 |
| `.github/kanata/review/SOURCES.md` | 規約の参考資料 |
| `.github/kanata/review/SOURCE.json` | 原本のコミットID、取り込んだ節、ファイルの照合用ハッシュ値 |

取り込む節はスクリプトの`SECTIONS`で指定します。文章の意味を変えず、節単位で取り込みます。
配布対象に含まれない補足資料へのリンクは、原本の同じコミットへのGitHubリンクに変わります。
その補足資料まで、オフラインで配布先に含まれるわけではありません。

## 自動で同期用PRを作る

`sync-review-rules`ワークフローは、原本の規約などが`kanata_workflow`の`main`へ取り込まれたときに動きます。
最初に原本のコミットを1つに決め、次の3リポジトリへ同じ版を配布します。

- `kanata_common`
- `kanata_core`
- `kanata_operation`

流れは「原本の更新をmainへ取り込む → 自動テスト → コピーを生成・照合 → 同期用PRを作成・更新」です。
同期先は[config/repositories.json](../config/repositories.json)の`github_repository`から取得します。
ローカルのPCに、3つのリポジトリを配置する必要はありません。

| 場面 | 動作 |
| --- | --- |
| 同期先のmainとの差分がある | `chore/sync-review-rules`ブランチでPRを作成 |
| 同じブランチのPRが開いている | そのPRを更新。更新ごとにPRを増やさない |
| 差分がない | 新しいPRを作らない |
| 配布ツールが衝突を検出する | そのリポジトリの同期を停止し、Actionsで失敗を表示 |

同期先へ書き込むのは、この資料の表にある生成ファイルだけです。
同期先のmainへ直接書き込んだり、PRを自動マージしたりしません。
生成したPRには、取得元のコミットと確認結果を日本語で記載します。同期先のCI結果は、PR上で別途確認します。

`chore/sync-review-rules`は自動同期専用です。手作業のコミットは加えないでください。
更新時に、このブランチの内容は生成した差分に置き換わります。
規約を直す場合は、`kanata_workflow`の原本を変更します。

通常のPRでは、規約配布・同期PRの準備処理をテストするだけです。他リポジトリへの書き込みは行いません。

### 初回に必要な認証設定

他リポジトリへブランチ・PRを作るため、追加の認証が必要です。
GitHubが提供する`GITHUB_TOKEN`は、通常、そのワークフローのリポジトリに権限が限定されます。
今回は、権限を細かく指定できるfine-grained personal access tokenを使います。

1. GitHubのアカウント設定から、fine-grained personal access tokenを作成します。
   作成方法は[GitHubの公式説明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)を参照してください。
2. Resource ownerは`YumaMatsumura`、Repository accessは対象の3リポジトリだけにします。
3. Repository permissionsで、`Contents`と`Pull requests`をそれぞれ`Read and write`にします。
   `Metadata`の読み取りは自動で含まれます。Actionsのワークフローを書き換える権限は不要です。
4. 有効期限を設定します。期限切れになった場合は、トークンを更新する必要があります。
5. **`kanata_workflow`**のSettings → Secrets and variables → Actionsで、
   `REVIEW_RULES_SYNC_TOKEN`という名前のRepository secretに保存します。

トークンの値は、ファイルやコミット、チャットへ記載しません。
トークンが未設定なら、自動同期はエラーを表示して停止します。ローカルの配布ツールは、トークンなしで使えます。

初回の設定後や再試行には、GitHubのActions → `sync-review-rules` → Run workflowで`main`を選びます。
手動実行でも、その時点の最新のmainを配布元にします。過去のイベントを再実行して、規約を古い版へ戻さないためです。
実行中の同期は途中で取り消さず、次の同期を待機させます。

自動同期の実行対象は、`rules/`、`SOURCES.md`、対象一覧、配布・PR準備スクリプト、同期ワークフローの変更です。
READMEだけの更新などでは起動しません。同期を始める前に、配布・PR準備処理の自動テストを実行します。

PRの作成・更新には[peter-evans/create-pull-request](https://github.com/peter-evans/create-pull-request)を使います。
追加トークンの利用により、生成したPRに対する通常のCIも起動できます。
認証方法の説明は[GitHubの公式資料](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)も参照してください。

## 手元で配布する

Python 3.10以上とGitを使います。追加のPythonパッケージや、ROS 2は不要です。
対象リポジトリは、すでに配置されているものだけを指定します。cloneやGitの初期化は行いません。
3つのROS 2リポジトリをすべて配置する必要もありません。

次は、ローカル開発環境で`kanata_common`へ配布する例です。

1. `kanata_workflow`のルートで、作成・更新するファイルを確認します。この段階では書き込みません。

   ```bash
   python3 scripts/sync_review_rules.py --target ../src/kanata_common
   ```

2. 内容を確認し、配布先に反映します。

   ```bash
   python3 scripts/sync_review_rules.py --target ../src/kanata_common --apply
   ```

3. 原本から作った内容と一致するか確認します。この検査は書き込みません。

   ```bash
   python3 scripts/sync_review_rules.py --target ../src/kanata_common --check
   ```

`kanata_core`や`kanata_operation`も、`--target`をそのリポジトリのルートに変えて実行します。
別の場所にあるリポジトリも指定できます。

`--apply`と`--check`は同時に指定できません。
`--check`は一致すれば終了コード0、不足・差分・衝突があれば1を返します。
通常の実行では書き込み予定だけを表示します。反映には`--apply`が必要です。

## 規約を更新する

配布元は、既定では`kanata_workflow`の`HEAD`、つまり現在のブランチの最新コミットです。
**まだコミットしていない規約の変更は取り込みません。**

1. 原本の規約を修正し、レビュー後にコミットします。
2. 配布するコミットを決め、上の手順で対象リポジトリを更新します。
3. 配布先の差分と検査結果を確認し、そのリポジトリの変更としてコミット・PRに含めます。

特定の版にそろえる場合は、各コマンドに`--source-ref`を付け、同じコミットIDを指定します。
例えば、`--source-ref`に`SOURCE.json`の`source_commit`の値を指定すると、その版との一致を検査できます。
そのコミットが、手元の`kanata_workflow`に存在する必要があります。

自動同期の認証設定が済んでいれば、mainへの取り込み後に同期PRが作られます。
各リポジトリのmainに反映されるのは、その同期PRをマージした後です。
PRの途中で参照する規約を勝手に差し替えず、取り込む版をPRの差分で確認できます。

## 既存のファイルがあるとき

配布ツールが管理していない`AGENTS.md`などがある場合や、配布後のファイルが編集されている場合は、上書きせず停止します。
`AGENTS.override.md`や、配布先のシンボリックリンクがある場合も停止します。
内容と指示の優先関係を確認してから、統合方法を決めてください。

手元で使う`sync_review_rules.py`は、ステージ操作・コミット・push・GitHubの設定変更を行いません。
Actionsでの自動同期は、生成ファイルを専用ブランチへコミット・pushし、PRを作成・更新する別の処理です。

## 自動レビューとの関係

最初は、ChatGPT／Codex側で設定するGitHubのCode Reviewに、この入口と規約を使わせます。
CodexのGitHub連携は、`AGENTS.md`の`Code Review Rules`からレビュー指示を読めます。
詳しくは[公式のGitHub連携の説明](https://learn.chatgpt.com/docs/third-party/github)を参照してください。

Code Reviewは重要度の高い不具合を中心に指摘します。命名や可読性を漏れなく点検する専用レビューとは、分けて考えます。
書式など機械で判定できる項目には、既存のCIを使います。

Code Reviewの有効化と、実際のPRで規約が使われるかの確認は別途行います。
ファイルの配置だけで、クラウド上のレビューが有効になったとは扱いません。

異常時の動作などの確認観点は、すでに[レビュー基準](../rules/review.md)に含まれます。
将来、観点別のレビューを順番に実行・集約する場合は、GitHub Actionsなどから同じ配布済み規約を参照できます。
今回、複数段階のレビュー実行や、ローカル用Skillのクラウドへの導入は行いません。

## 配布ツールの自動テスト

`kanata_workflow`のルートで実行します。

```bash
python3 -B tests/test_review_rules.py -v
python3 -B tests/test_review_rules_pr.py -v
```

一時フォルダのGitリポジトリを使い、規約の取得元の固定、単独リポジトリへの配置、既存ファイルの保護、更新と失敗時の復元を確認します。
同期先一覧の取得、同期PR用の文章と対象ファイルの生成、差分がない場合や既存の変更がある場合も確認します。
GitHub Actionsの`review-rules`でも同じテストを実行します。これらのテストでは、GitHubへの書き込みやAIによるレビューは実行しません。
トークン設定後の実際のPR作成・更新は、GitHub上で別途確認します。
