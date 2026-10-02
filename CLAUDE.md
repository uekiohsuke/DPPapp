# CLAUDE.md

## 仕様
- 仕様書は [conlang-app-spec.md](conlang-app-spec.md)。仕様変更は、このファイルの更新として記録される(詳細は別のチャットで詰めている)。作業の前に必ず読み、記述と食い違う実装をしない
- 作る順序は仕様書 §7 のマイルストーン(M0〜M7)。1回の依頼で1段階だけ進める
- 各段階の完了条件は、実装より先にテストとして書く
- M3(規則の形式)のように「本人と相談して決める」段階は、案を出して確認を取ってから進める
- 【仮】【要確認】【保留】の項目を実装で勝手に確定させない。必要なら質問する

## 構成の決まりごと
- `conlang/core/` は言語に依存しない土台。言語別の機能(音素、造語規則、形態素分解など)をここに書かない
- 言語別の機能は `conlang/languages/<言語>/` に置き、`conlang/core/registry.py` の登録口から土台に足す
- 画面(`conlang/gui/`、M2 から)はコアを呼ぶだけ。検査やチェックのロジックを画面に書かない
- コアは画面なしで CLI(`conlang ...`)から動かせるようにする
- 依存はできるだけ標準ライブラリ。GUI は PySide6

## データ
- 既存の辞書は書き換える前に必ずバックアップを取る(`conlang/core/backup.py`)。元の辞書ファイルは書き換えない(取り込みはコピー)
- 辞書は zpdic 形式(`words` / `zpdic` / `snoj`)。未知のキーも含め、読んだ内容をすべて保ったまま書き戻す
- 規則は言語ごとの YAML(プロジェクトの `rules.yaml`、元は `data/pute-rules.yaml`)。データで書けるものは YAML、手続きはコード。YAML の読み込みと status の一覧は `conlang/core/rules.py`、中身の解釈は言語別機能(`conlang/languages/pute/rules.py`)
- 規則ファイルと文法 md は役割が違う(仕様書 4.7)。片方からもう片方を生成しない。表の食い違いはコード(`pute/grammar_check.py`)、文章の矛盾は LLM の候補で見つける
- 整合性チェック: 共通の検査は `core/validate.py`(段階は「誤り」「注意」)、言語別の検査は registry の `check_dictionary` で足す(ピュテ語は `pute/consistency.py`)。修正済みの辞書で「誤り」が0件になること(誤検出がない)を保つ
- LLM の呼び出しは、プロンプトと答えを `core/llm_log.py` でプロジェクトの `llm_log/` に残す
- `conlang/languages/pute/zougo.py` は試作を取り込んだもの。試作が更新されたら、ロジックを取り込み直す(規則はモジュール全体の値なので、使う前に `apply_rules()` で入れる)
- 創作データ(`data/`、`projects/`、文法の Markdown)は git に入れない。テストには `tests/fixtures/` の架空データを使い、実データが必要なテストは `data/` にあるときだけ動かす(skipif)

## 開発
- Python 3.11、venv は `.venv`
- テスト: `.venv\Scripts\python -m pytest`
- 画面と文書は日本語
- `prototype/pute_zougo.py` は元の試作。比較用に変えずに残す
