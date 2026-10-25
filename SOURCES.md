# 規約の参考資料

KANATAの規約・作業手順で参考にした資料と、その範囲をまとめています。
守る規約は[rules/](rules/)に記載しています。参考資料の内容すべてを採用するものではありません。

## AIの設定とレビュー

| 参考資料 | 参考にした内容 |
| --- | --- |
| [AGENTS.mdの公式説明](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Codexが作業指示を読む範囲 |
| [Skillの公式説明](https://learn.chatgpt.com/docs/build-skills) | Skillの構成、リンク経由の読み込み、呼び出し方と設定 |
| [Anthropic公式のコードレビュー手順](https://github.com/anthropics/claude-code/blob/main/plugins/code-review/commands/code-review.md) | 指摘の根拠の再確認と、重複する指摘の整理 |
| [OpenAIのレビュー規約の記事](https://developers.openai.com/blog/custom-code-review-rules-for-codex) | 具体的な規約の適用範囲と、レビュー・CIの役割分担 |

Codexの設定資料は、他のAIツールでも同じ設定が使えることを示すものではありません。
Anthropicの手順にある、特定の入力・状態で起きる問題の除外や、固定人数・固定回数のレビューは採用していません。
KANATAのレビュー基準は[review.md](rules/review.md)を参照してください。

## コードとテスト

| 参考資料 | 参考にした内容 |
| --- | --- |
| [ROS 2 Jazzyのコードスタイル](https://docs.ros.org/en/jazzy/The-ROS2-Project/Contributing/Code-Style-Language-Versions.html) | KANATAで定めていないC++の書き方 |
| [C++ Core Guidelines](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines) | 設計、リソース管理、安全な書き方 |
| [clang-tidyの公式説明](https://clang.llvm.org/extra/clang-tidy/) | 静的解析の用途と設定 |
| [AutowareのC++規約](https://docs.autoware.org/main/contributing/coding-guidelines/languages/cpp/) | include、命名、Eigenの式、ログの扱い |
| [Autowareのlaunch規約](https://docs.autoware.org/main/contributing/coding-guidelines/ros-nodes/launch-files/) | 個別パッケージと統合用launchの役割、設定の受け渡し |
| [Autowareのメッセージ規約](https://docs.autoware.org/main/contributing/coding-guidelines/ros-nodes/message-guidelines/) | 値の説明、単位、無効値と状態定数 |
| [ROS 2のインターフェース定義仕様](https://design.ros2.org/articles/legacy_interface_definition.html) | `.msg`・`.srv`・`.action`の形式、命名、配列、既定値 |
| [REP-103](https://github.com/ros-infrastructure/rep/blob/master/rep-0103.rst) | 標準単位と座標系 |
| [Autowareのパラメータ規約](https://docs.autoware.org/main/contributing/coding-guidelines/ros-nodes/parameters/) | コードとYAMLの整合、設定値の説明、必須指定 |
| [ROS 2 Jazzyのパラメータの説明](https://github.com/ros2/ros2_documentation/blob/jazzy/source/Concepts/Basic/About-Parameters.rst) | 実行中の変更の検証・拒否と、受理後の反映 |
| [Autowareのtopic・名前空間の規約](https://docs.autoware.org/main/contributing/coding-guidelines/ros-nodes/topic-namespaces/) | 自作ノードの入出力・デバッグ用topicと、launchでの接続 |
| [ROS 2のtopic・service名の仕様](https://design.ros2.org/articles/topic_and_service_names.html) | 相対名・絶対名・`~`とROS名前空間の関係 |
| [ROS 2のremapの仕様](https://design.ros2.org/articles/static_remapping.html) | 起動時の名前の置き換え |
| [Autowareの単体テストの指針](https://docs.autoware.org/main/contributing/testing-guidelines/unit-testing/) | amentへの登録、検証マクロ、ROS通信を使うテストの分離 |
| [GoogleTest Primer](https://google.github.io/googletest/primer.html) | テストの命名、`EXPECT_*`・`ASSERT_*`、テストの独立性 |
| [CMakeの設定範囲の説明](https://cmake.org/cmake/help/v3.28/command/target_include_directories.html) | `PUBLIC`・`PRIVATE`・`INTERFACE`の適用範囲 |

Autowareのリポジトリ構成・launchの階層数・パラメータファイルの分割を、そのまま求めるものではありません。
配列を一律に上限なしにする方針や、すべてのパラメータを必須指定にする方針も採用していません。
JSON Schema・sync-paramsの利用を前提とせず、AUTOSAR C++14 Guidelinesを必須の参照先には含めません。
具体的な採用範囲と参照先の優先順位は[coding.md](rules/coding.md)を参照してください。

## Gitと検証ツール

| 参考資料 | 参考にした内容 |
| --- | --- |
| [AutowareのPR規約](https://docs.autoware.org/main/contributing/pull-request-guidelines/) | PRの説明方法 |
| [Autowareのコミット規約](https://docs.autoware.org/main/contributing/pull-request-guidelines/commit-guidelines/) | ブランチ名と`Signed-off-by`の扱い |
| [pre-commit](https://pre-commit.com/) | 書式・コードの検査方法 |

Git運用と共著表記は[git.md](rules/git.md)、検証方法は[testing.md](rules/testing.md)にまとめています。
