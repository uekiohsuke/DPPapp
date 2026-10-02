# conlang — 人工言語創作アプリ

自分の人工言語の文法・辞書・造語を1か所で整理して育てるための、自分専用のデスクトップアプリです(PySide6)。
最初に対応する言語はピュテ語です。仕様は [conlang-app-spec.md](conlang-app-spec.md) にあります。

## 進み具合(仕様書 §7)

| 段階 | 内容 | 状態 |
|---|---|---|
| M0 | 試作の整理 | 済み(`prototype/pute_zougo.py`、`conlang pute ...`) |
| M1 | コアと辞書(CLI) | 済み |
| M2 | 辞書の画面 | |
| M3 | 規則の形式を決める | |
| M4 | 整合性チェック | |
| M5 | 造語支援 | |
| M6 | LLM 連携 | |
| M7 | 文法文書の管理 | |

## セットアップ(Windows)

```powershell
python -m venv .venv          # Python 3.11
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

## データの置き場所

辞書や文法などの創作データは git に入れません(`.gitignore`)。

- `data/` … 元のデータ(secondpute.json、uri.json、pute2-grammar.md、uri-grammar.md)。アプリはここを書き換えない
- `projects/` … 言語プロジェクト(`conlang new` で作る)

テストは `tests/fixtures/` の架空の小さな辞書で動きます。`data/` に実データがあれば、実データを使うテストも動きます。

## 使い方(CLI)

```powershell
conlang new projects\pute --name ピュテ語 --language pute
conlang import projects\pute data\secondpute.json   # 元の辞書はコピーするだけ
conlang info projects\pute
conlang save projects\pute                          # 保存の前に backup\ へバックアップ
conlang verify data\uri.json                        # 読んで書き戻しても壊れないか確かめる

conlang pute --project projects\pute find 力
conlang pute --project projects\pute check 節点 外
conlang pute --project projects\pute suggest 辺 数
conlang pute --project projects\pute decompose 重力加速度 --prompt-only
```

辞書は、元のファイルの書式(Python 風の字下げ / zpdic の書き出し形式、改行コード、末尾の改行)に合わせて書き戻すので、
内容を変えていなければ保存してもバイト列が変わりません。
