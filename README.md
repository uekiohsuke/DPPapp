# conlang — 人工言語創作アプリ

自分の人工言語の文法・辞書・造語を1か所で整理して育てるための、自分専用のデスクトップアプリです(PySide6)。
最初に対応する言語はピュテ語です。仕様は [conlang-app-spec.md](conlang-app-spec.md) にあります。

## 進み具合(仕様書 §7)

| 段階 | 内容 | 状態 |
|---|---|---|
| M0 | 試作の整理 | 済み(`prototype/pute_zougo.py`、`conlang pute ...`) |
| M1 | コアと辞書(CLI) | 済み |
| M2 | 辞書の画面 | 済み(`conlang gui`) |
| M3 | 規則の形式を決める | YAML で決定。読み込みと利用は済み(全項目の確認は本人) |
| M4 | 整合性チェック | 済み(`conlang check`、`conlang pute grammar-check`) |
| M5 | 造語支援 | |
| M6 | LLM 連携 | |
| M7 | 文法文書の管理 | |

## セットアップ(Windows)

```powershell
python -m venv .venv          # Python 3.11
.venv\Scripts\python -m pip install -e ".[dev,gui]"
.venv\Scripts\python -m pytest
```

## 画面

```powershell
.venv\Scripts\conlang gui projects\pute    # フォルダを省くと、前に開いたプロジェクトを開く
```

- 左: 検索と一覧。検索する場所(見出し語・訳語・内容・タグ)と一致のしかたを選べる。内容は「語義」「語源」などの見出しで絞れる。列の見出しを押すと並べ替える
- 右: 選んだ語の閲覧。「編集」(F2 かダブルクリック)で編集に切り替え、「適用」で辞書に反映する
- 下: 警告。「誤り」(誤記、旧用語、音素、同じ綴り など)を赤で先に、「注意」(空の項目、似た綴り)をあとに出す。ダブルクリックでその語へ移動する
- 下の「規則」タブ: 規則ファイルの「決定」以外の規則、文法文書との表の食い違い、規則ファイルの点検の結果。「ファイル → 規則ファイルを取り込む」で読み込む

LLM による文章の記述の検査は、答えを候補として出すだけで、「問題なし」の保証にはしません。文法文書と規則ファイルが前回から変わっていなければ、API を呼びません(`--force` で呼ぶ)。プロンプトと答えは、プロジェクトの `llm_log\` に残ります。
- 「ファイル → 保存」(Ctrl+S)で、プロジェクトの dictionary.json に zpdic 形式で保存する。保存の前に backup\ へバックアップを取る
- 「ファイル → zpdic 形式で書き出す」で、プロジェクトの外へ書き出せる。「新しい語」は Ctrl+N

## データの置き場所

辞書や文法などの創作データは git に入れません(`.gitignore`)。

- `data/` … 元のデータ(secondpute.json、secondpute_q_with_typos.json、uri.json、pute-rules.yaml、pute2-grammar.md、uri-grammar.md)。アプリはここを書き換えない
- `projects/` … 言語プロジェクト(`conlang new` で作る)

テストは `tests/fixtures/` の架空の小さな辞書で動きます。`data/` に実データがあれば、実データを使うテストも動きます。

## 使い方(CLI)

```powershell
conlang new projects\pute --name ピュテ語 --language pute
conlang import projects\pute data\secondpute.json   # 元の辞書はコピーするだけ
conlang info projects\pute
conlang save projects\pute                          # 保存の前に backup\ へバックアップ
conlang verify data\uri.json                        # 読んで書き戻しても壊れないか確かめる

conlang rules import projects\pute data\pute-rules.yaml   # 規則ファイルをプロジェクトの rules.yaml にコピー
conlang rules show projects\pute                    # 「決定」以外の規則の一覧と、規則ファイルの点検

conlang grammar import projects\pute data\pute2-grammar.md   # 文法文書を grammar\ にコピー

conlang check projects\pute                          # 辞書の整合性チェック(誤記、旧用語、音素、似た綴り)
conlang check data\secondpute_q_with_typos.json --rules data\pute-rules.yaml --language pute
conlang pute --project projects\pute grammar-check   # 文法 md の目印と規則ファイルの ref の照合、表の照合(コード)
conlang pute --project projects\pute grammar-check --prompt-only        # 文章の記述を LLM に調べさせるプロンプト
conlang pute --project projects\pute grammar-check --response 答え.json # 別のチャットの答えを読み込む
conlang pute --project projects\pute grammar-check --llm                # 設定した LLM に問い合わせる

conlang llm config --url http://192.168.0.178:11434/v1 --model qwen3.5:27b --reasoning-effort none   # LLM の接続先(この PC の設定)
conlang llm models                                   # 接続先のモデルの一覧
conlang llm ask "こんにちは"                          # 接続の確認

conlang pute --project projects\pute inflect noun verb    # 規則から活用表を作る
conlang pute --project projects\pute gen 10 --seed 1      # 新しい基本詞の候補
conlang pute --project projects\pute find 力
conlang pute --project projects\pute check 節点 外
conlang pute --project projects\pute suggest 辺 数
conlang pute --project projects\pute decompose 重力加速度 --prompt-only
```

文法 md と規則ファイルは、節の番号ではなく、md の `<!-- rule: ID -->` と規則ファイルの `ref` で対応づけます。章立てや節の番号を変えても、照合は壊れません。

LLM の接続先とモデルは `%APPDATA%\conlang\llm.json` に保存します(リポジトリには入りません)。環境変数 `CONLANG_LLM_URL` / `CONLANG_LLM_MODEL` / `CONLANG_LLM_KEY` があれば、そちらが優先です。

辞書は、元のファイルの書式(Python 風の字下げ / zpdic の書き出し形式、改行コード、末尾の改行)に合わせて書き戻すので、
内容を変えていなければ保存してもバイト列が変わりません。
