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
| M4 | 整合性チェック | |
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
- 下: 警告(空の見出し語・訳語なし・同じ綴り・id の重複など)。ダブルクリックでその語へ移動する
- 下の「規則」タブ: 規則ファイルの「決定」以外の規則と、言語別の点検の結果。「ファイル → 規則ファイルを取り込む」で読み込む
- 「ファイル → 保存」(Ctrl+S)で、プロジェクトの dictionary.json に zpdic 形式で保存する。保存の前に backup\ へバックアップを取る
- 「ファイル → zpdic 形式で書き出す」で、プロジェクトの外へ書き出せる。「新しい語」は Ctrl+N

## データの置き場所

辞書や文法などの創作データは git に入れません(`.gitignore`)。

- `data/` … 元のデータ(secondpute.json、uri.json、pute-rules.yaml、pute2-grammar.md、uri-grammar.md)。アプリはここを書き換えない
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

conlang pute --project projects\pute inflect noun verb    # 規則から活用表を作る
conlang pute --project projects\pute gen 10 --seed 1      # 新しい基本詞の候補
conlang pute --project projects\pute find 力
conlang pute --project projects\pute check 節点 外
conlang pute --project projects\pute suggest 辺 数
conlang pute --project projects\pute decompose 重力加速度 --prompt-only
```

辞書は、元のファイルの書式(Python 風の字下げ / zpdic の書き出し形式、改行コード、末尾の改行)に合わせて書き戻すので、
内容を変えていなければ保存してもバイト列が変わりません。
