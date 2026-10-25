# ローカル開発環境への導入

`setup.py`で、ワークスペースからKANATAの規約とCodex用Skillを参照できるようにします。
元の資料をコピーする代わりに、資料の場所を指すシンボリックリンクを作ります。

## 準備

LinuxとPython 3.10以上を使います。通常の開発環境はUbuntu 24.04・Python 3.12です。
追加のPythonパッケージや、ROS 2のインストールは不要です。

既存のワークスペースに`src/`を用意し、`kanata_workflow`を配置してください。
以下は`~/kanata_ws/kanata_workflow`に置いた場合の例です。

ROS 2のリポジトリは、行う作業と依存関係に合わせて用意します。
common単独、common＋core、common＋operation、3つすべての配置に対応します。
ここでのcommon・core・operationは、`kanata_common`・`kanata_core`・`kanata_operation`です。

このセットアップだけを行う場合は、`src/`が空でも構いません。
候補一覧にあるリポジトリを自動で取得したり、すべての配置を必須にしたりしません。

## 導入する

1. リポジトリのルートへ移動し、作成予定のリンクを確認します。この段階では書き込みません。

   ```bash
   cd ~/kanata_ws/kanata_workflow
   python3 scripts/setup.py --workspace ~/kanata_ws
   ```

2. 表示された内容を確認してから、リンクを作ります。

   ```bash
   python3 scripts/setup.py --workspace ~/kanata_ws --apply
   ```

3. リンクの配置を確認します。この検査も書き込みません。

   ```bash
   python3 scripts/setup.py --workspace ~/kanata_ws --check
   ```

`--apply`と`--check`は同時に指定できません。
同じリンクがすでにあれば、そのまま使います。繰り返し実行しても作り直しません。

作成するリンクは次の7つです。Skillは6つそれぞれにリンクを作ります。

| 配置先（ワークスペース基準） | 参照先 |
| --- | --- |
| `AGENTS.md` | `kanata_workflow/AGENTS.md` |
| `.agents/skills/kanata-<作業名>` | `kanata_workflow/skills/kanata-<作業名>` |

`kanata_workflow`は別の場所に置くこともできます。その場合は、そこにある`setup.py`を実行してください。
リンク作成後にリポジトリを移動すると、リンクが切れることがあります。

## 結果の見方

- `[PRESENT]`は、候補の場所にディレクトリと`.git`があることを表します。
- `[NOT PLACED] ... (optional)`は未配置の候補です。警告や検査失敗にはしません。
- `WARNING`は、配置先がファイルになっている場合や、配置済みのディレクトリに`.git`がない場合などの注意です。
  内容を確認してください。この案内だけで、ビルドやGitの状態を検査したことにはなりません。
- 既存の`AGENTS.md`やSkillと衝突する場合は、上書きせずに停止します。
  `AGENTS.override.md`がある場合や、候補一覧が読めない・形式が不正な場合も停止します。

`--check`は、必要なリンクがそろっていれば終了コード0、リンクが不足している場合や停止条件に該当する場合は1を返します。
配置していない候補リポジトリの数は、この判定に影響しません。

## AIが使えるか確認する

Codexでワークスペース（例：`~/kanata_ws`）を開き、新しい会話で[導入確認用の依頼文](../BOOTSTRAP_PROMPT.md)を使ってください。
子リポジトリだけを開いた場合、ワークスペース側の入口やSkillが自動で読まれるとは限りません。

このスクリプトが確認するのはファイルとリンクの配置です。AIによる規約の読み込みやSkillの実行までは検査しません。
他のAIを使う場合は、そのツールでの読み込ませ方を確認してください。

配置方法は、OpenAI公式の[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)と[Skill](https://learn.chatgpt.com/docs/build-skills)の説明を参照しています。

## 自動テスト

リポジトリのルートで実行します。Pythonの標準ライブラリだけを使い、一時フォルダで検証します。

```bash
python3 -B tests/test_setup.py -v
```

配置の組み合わせ、既存ファイルの保護、繰り返し実行、途中で失敗した場合の後片付けを確認します。
GitHub Actionsの`local-setup`でも同じテストを実行します。実際のワークスペースへの導入や、AIの起動は行いません。
