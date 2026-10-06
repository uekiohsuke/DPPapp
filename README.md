# conlang — 人工言語創作アプリ

自分の人工言語の文法・辞書・造語を1か所で整理して育てるための、自分専用のデスクトップアプリです(PySide6)。
言語別の機能は、ピュテ語(造語支援・整合性チェック・活用表など)、ウリ語(基本の部分: 現代の転写、音節、辞書の検査)、
ミャミュ語(基本の部分: 音素と音の連なり、動詞の枠での組み立てと分解、数)があります。
仕様は [conlang-app-spec.md](conlang-app-spec.md) にあります。

## 進み具合(仕様書 §7)

| 段階 | 内容 | 状態 |
|---|---|---|
| M0 | 試作の整理 | 済み(`prototype/pute_zougo.py`、`conlang pute ...`) |
| M1 | コアと辞書(CLI) | 済み |
| M2 | 辞書の画面 | 済み(`conlang gui`) |
| M3 | 規則の形式を決める | YAML で決定。読み込みと利用は済み(全項目の確認は本人) |
| M4 | 整合性チェック | 済み(`conlang check`、`conlang pute grammar-check`) |
| M5 | 造語支援 | 済み(`conlang pute analyze / shorten / long / gen …`、画面の「造語」欄) |
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
.venv\Scripts\conlang shortcut             # デスクトップとスタートメニューに「人工言語創作アプリ」のショートカットを作る
```

ショートカット(画面の「設定」メニューからも作れる)は、コンソールを出さずに起動し、前に開いたプロジェクトを開きます。
`--project projects\uri --name ウリ語` のように、決まったプロジェクトを開くショートカットも作れます。
venv を作り直したり、リポジトリの場所を変えたりしたときは、もう一度作ってください。
コンソールがないので、思わぬエラーは画面に出し、`%APPDATA%\conlang\error.log` にも残します。

- 上の「プロジェクト」: 開いたことのあるプロジェクト(言語)を切り替える。言語別の欄も、その言語のものに替わる
- 「辞書」タブと「文法」タブ: 文法タブでは、プロジェクトの grammar\ の Markdown を読める(目次から移動、検索、状態タグの色分けと数、規則の目印の表示)。「エディタで開く」で直すと、自動で読み直す
- 左: 検索と一覧。言語に表示の切り替えがあれば(ウリ語の「現代の転写」)、見出し語の表示を切り替えられる(辞書の綴りは変えない)。検索する場所(見出し語・訳語・内容・タグ)と一致のしかたを選べる。内容は「語義」「語源」などの見出しで絞れる。列の見出しを押すと並べ替える
- 右: 選んだ語の閲覧。「編集」(F2 かダブルクリック)で編集に切り替え、「適用」で辞書に反映する
- 下: 警告。「誤り」(誤記、旧用語、音素、同じ綴り など)を赤で先に、「注意」(空の項目、似た綴り)をあとに出す。ダブルクリックでその語へ移動する
- 「設定 → LLM の設定」: 接続先、モデル(「モデルの一覧を取得」で接続先のモデルから選ぶ。Ollama なら大きさと「考える過程あり」も出る)、考える過程の量、温度、待ち時間。「接続を試す」で確かめられる。右下に今のモデルが出る
- LLM の問い合わせは裏で動くので、待っているあいだも辞書の閲覧・編集ができる。経過時間が出て、「中止」で結果を捨てられる
- 下の「造語(ピュテ語)」タブ: 検索、組み合わせの検査、提案、形態素分解、短縮の候補、長大語、基本詞の候補、LLM による分解。保存前の編集も使う
  - LLM による分解は、日本語の語を字面で分けるのではなく、ピュテ語でその概念をどう組み立てるかを考えさせる。意味・説明、分野、区別したい意味(同字異義)を書く欄がある。答えには LLM の解釈が付くので、取り違えていないか確かめられる
- 下の「規則」タブ: 上に、文法文書との表の照合と規則ファイルの点検の結果。その下のタブで切り替える
  - 「規則の状態」: 「決定」以外の規則(「ファイル → 規則ファイルを取り込む」で読み込む)
  - 「文章を LLM で調べる」: 文章の目印を LLM に調べさせる
  - 「言語の機能」: その言語の CLI の機能(`conlang <言語> …`)を、選んで実行する。ミャミュ語は動詞の組み立て・分解、音の連なり、
    音素、接辞の一覧、数。ウリ語は接頭辞と辞書で読む、現代の転写、音節、訳語から探す、情詞。ピュテ語は活用表と造語の各機能。
    「例を入れる」で引数の例が入る。保存前の編集も使う
- 語の編集: 訳語・変化形・関連語の「区分」と、内容の「見出し」は、辞書に既にあるもの(よく使われている順)から選べる。新しいものも書ける

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
conlang pute --project projects\pute analyze thaidra kethjadrwoqakushavo   # 形態素分解('~' は母音をまとめた境目)
conlang pute --project projects\pute shorten eshkiki judra   # 短縮形を使った候補
conlang pute --project projects\pute long                    # 長大語(20文字以上)と短縮案
conlang pute --project projects\pute decompose 重力加速度    # LLM で概念を要素に分け、未収録の要素に基本詞の候補
conlang pute --project projects\pute decompose 場 --field 物理学 --description "空間の各点に物理量が割り当てられたもの" --distinguish "場所"
                                                             # 説明・分野・区別したい意味を添えると、同字異義を取り違えにくい
conlang pute --project projects\pute decompose 重力加速度 --prompt-only
```

文法 md と規則ファイルは、節の番号ではなく、md の `<!-- rule: ID -->` と規則ファイルの `ref` で対応づけます。章立てや節の番号を変えても、照合は壊れません。

LLM の接続先とモデルは `%APPDATA%\conlang\llm.json` に保存します(リポジトリには入りません)。環境変数 `CONLANG_LLM_URL` / `CONLANG_LLM_MODEL` / `CONLANG_LLM_KEY` があれば、そちらが優先です。

ウリ語(`--language uri` のプロジェクト):

```powershell
conlang new projects\uri --name ウリ語 --language uri
conlang import projects\uri data\uri.json
conlang grammar import projects\uri data\uri-grammar.md
conlang rules import projects\uri data\uri-rules.yaml
conlang grammar check projects\uri                         # 文法 md と規則ファイルの照合(どの言語でも使える)
conlang uri --project projects\uri particles               # 情詞の一覧と、辞書にあるか
conlang uri --project projects\uri modern SuKaHuDu FoTONe  # 辞書の旧表記 → 現代の転写(sukahudu、fotoone)
conlang uri --project projects\uri syllables KanTi ReWing  # 音節(CV、CVn、CVng)
conlang uri --project projects\uri analyze LoRoPu          # 接頭辞(lo-)と残り(ropu)を、辞書と照らす
conlang uri --project projects\uri find 女装
conlang check projects\uri                                 # 音節に分けられない語(近現代の形には現代の形を添える)、旧表記の大文字の位置、
                                                           # 接頭辞、iyi・Cuwu の並び、情詞の一覧との照合(規則ファイルの checks)
```

ミャミュ語(`--language myamyu` のプロジェクト。辞書はまだないので、空の辞書から始まる):

```powershell
conlang new projects\myamyu --name ミャミュ語 --language myamyu
conlang rules import projects\myamyu data\myamyu-rules.yaml
conlang grammar import projects\myamyu data\myamyu-grammar.md
conlang grammar check projects\myamyu                      # 文法 md と規則ファイルの照合
conlang rules show projects\myamyu                         # 規則ファイルの中の点検(試作の SELF_CHECKS)も出る
conlang myamyu --project projects\myamyu segment lemjgo    # 音素(sh・mj は1つの子音)
conlang myamyu --project projects\myamyu sound gaf baz ssa # 音の連なりの規則(→ gabazsa)
conlang myamyu --project projects\myamyu verb gaz --tense 未来 --voice 受動態 --aspect 起動相 --subject 三人称単数
conlang myamyu --project projects\myamyu parse ze-gaz-af-ol-esh-ol   # 枠に分ける(同形の ol を位置で読み分ける)
conlang myamyu --project projects\myamyu affixes           # 接辞の一覧
conlang myamyu --project projects\myamyu number 7          # 数の語
```

辞書は、元のファイルの書式(Python 風の字下げ / zpdic の書き出し形式、改行コード、末尾の改行)に合わせて書き戻すので、
内容を変えていなければ保存してもバイト列が変わりません。
