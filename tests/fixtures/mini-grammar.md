# 架空語 文法(テスト用。mini_rules.yaml と食い違いがないように書いてある)

## 1. 音韻

### 1.1 母音(6個)

<!-- rule: phonology.vowels -->
| 転写 | a | e | i | o | u | wo |
|---|---|---|---|---|---|---|
| 音 | [a] | [e] | [i] | [o] | [u] | [ɤ] |

### 1.2 子音(15個)

<!-- rule: phonology.consonants -->
| 系列 | 転写 = 音 |
|---|---|
| S音 | s [s]、sh [ʃ]、sch [ɕtɕ]、sx [x] |
| K音 | k [k]、tch [t͡ʃ] |
| T音 | t [t]、tr [ʈ]、th [θ]、dr [ɖ] |
| D音 | d [d]、j [d͡ʒ]、q [ɢ] |
| V音 | v [v]、b [b] |

## 2. 語の種類

### 2.2 動詞化の接頭辞

<!-- rule: affixes.verbalizer -->
| 接頭辞 | 働き |
|---|---|
| sa- | 動詞化。説明の続き |

- sa- は語幹の前に付く

### 2.5 複合語

<!-- rule: compounding.rules -->
- 大本の概念を先頭に置く
- 同じ母音が並ぶときは1つにまとめる【仮】

## 8. 活用

### 8.1 名詞の活用

<!-- rule: inflection.noun.tense -->
| 形 | 語尾 |
|---|---|
| 常態 | 語幹のまま |
| 現在 | -as |
| 過去 | -es |

<!-- rule: inflection.noun.state -->
| 形 | 語尾 |
|---|---|
| 一般形 | 語幹のまま |
| 高状態形 | -b |

| 状態形 | 常態 | 現在 | 過去 |
|---|---|---|---|
| 一般形 | X | X-as | X-es |
| 高状態形 | X-b | X-bas | X-bes |

### 8.2 動詞の活用

<!-- rule: inflection.verb.tense -->
| 形 | 語尾 |
|---|---|
| 常態 | 語幹のまま |
| 現在 | -av |
| 過去 | -ev |
| 否定 | -ov |

<!-- rule: inflection.verb.state -->
| 形 | 語尾 |
|---|---|
| 一般形 | 語幹のまま |
| 高状態形 | -d |
| 低状態形 | -q |

| 状態形 | 常態 | 現在 | 過去 | 否定 |
|---|---|---|---|---|
| 一般形 | X | X-av | X-ev | X-ov |
| 高状態形 | X-d | X-dav | X-dev | X-dov |
| 低状態形 | X-q | X-qav | X-qev | X-qov |

### 8.3 形容詞と副詞の活用

<!-- rule: inflection.classes -->
- 形容詞は名詞と、副詞は動詞と同じ活用
- ただし、一般形の常態は、形容詞が -wosh、副詞が -woj になる
