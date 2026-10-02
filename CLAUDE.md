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
- 文法 md と規則ファイルの対応づけは、節番号ではなく目印 `<!-- rule: ID -->` と `ref` キーで行う(`core/rule_docs.py`)。検査のコードに節番号を書かない。規則を足すときは目印と ref の両方を足す
- 整合性チェック: 共通の検査は `core/validate.py`(段階は「誤り」「注意」)、言語別の検査は registry の `check_dictionary` で足す(ピュテ語は `pute/consistency.py`)。修正済みの辞書で「誤り」が0件になること(誤検出がない)を保つ
- LLM の呼び出しは、プロンプトと答えを `core/llm_log.py` でプロジェクトの `llm_log/` に残す
- LLM は OpenAI 互換の API を `core/llm.py` で呼ぶ。本人の環境はローカルの Ollama(http://192.168.0.178:11434/v1)。接続先とモデルは利用者の設定(%APPDATA%\conlang\llm.json、`conlang llm config`)で、リポジトリに書かない。テストは偽のサーバーで行い、本物の LLM を前提にしない
- 造語支援は `conlang/languages/pute/coining.py`(規則ファイルから動くエンジン。結果はデータで返す)と `cli_coining.py`(表示)。試作 `prototype/pute_zougo.py` が更新されたら、その変更をエンジンに移す。規則の解釈は `lang.py`(PuteLang)に集め、整合性チェックと共有する
- 言語別の画面部品は registry の `gui_panels` から足す(ピュテ語は `gui_coining.py`)。土台の画面に言語別のコードを書かない
- ウリ語は `conlang/languages/uri/`(基本の部分: 旧表記 → 現代の転写、音節 CV/CVn/CVng、接頭辞、辞書の検査、文法 md との照合)。辞書は旧表記で時代も混在するので、ウリ語の検査はすべて「注意」。規則は `data/uri-rules.yaml`(本人が書いたもの)。検査は規則ファイルの `checks` にあるものだけ行う
- 文法 md と規則ファイルの照合の進め方は `core/grammar_check.py`(言語共通)。言語ごとに違うのは表の比べ方だけで、registry の `grammar_table_checks` に置く(ピュテ語 `pute/grammar_check.py`、ウリ語 `uri/grammar_check.py`。試作 `prototype/check_rules_docs.py` の PUTE_CHECKS / URI_CHECKS に対応)
- 見出し語の表示の切り替え(仕様書 4.9)は registry の `transcriptions`。辞書の綴りは書き換えない
- クラス接頭辞(辞書で区分が「クラス」の語。scha など)は分野を区別するための接頭辞で、核にはならない(本人の決定)
- 画面で LLM など時間のかかる処理は、`conlang/gui/tasks.py` の `run_task` で裏のスレッドに出し、画面を止めない。裏の処理では画面の部品に触らず、辞書は写しを渡す。出力を集めるときは `capture`(スレッドごと。`contextlib.redirect_stdout` はスレッドをまたいで混ざるので使わない)
- 創作データ(`data/`、`projects/`、文法の Markdown)は git に入れない。テストには `tests/fixtures/` の架空データを使い、実データが必要なテストは `data/` にあるときだけ動かす(skipif)

## 開発
- Python 3.11、venv は `.venv`
- テスト: `.venv\Scripts\python -m pytest`
- 画面と文書は日本語
- `prototype/pute_zougo.py` は元の試作。比較用に変えずに残す
