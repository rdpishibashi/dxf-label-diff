# TECHNICAL.md — DXF-label-diff

## 概要

最大 5 ペアの DXF ファイルを比較し、ラベル差分を色分け Excel で出力する Streamlit アプリ。
座標比較・ラベル変更ペア抽出・未変更ラベル抽出など高度な差分分析オプションを持つ。

---

## ディレクトリ構成

```
DXF-label-diff/
├── app.py                  # Streamlit エントリポイント
├── config.txt              # デフォルトプレフィックスリスト（改行区切り）
├── requirements.txt
├── utils/
│   ├── compare_labels.py   # ラベル比較コア（compare_labels_multi）
│   ├── extract_labels.py   # DXF ラベル抽出（共有モジュール）
│   └── common_utils.py     # 共通ユーティリティ（共有モジュール）
```

---

## アーキテクチャ

### データフロー

```
ファイルペア登録（最大 5 ペア）
  → [オプション設定]
  → save_uploadedfile() × ペア数
  → compare_labels_multi()
      → Excel バイナリ（差分比較）
      → Excel バイナリ（未変更ラベル）  ← detect_label_changes 時のみ
  → st.download_button() × 1〜2 個
```

### `compare_labels_multi()` の処理

1. 各ペアに対して `extract_labels()` を実行
2. A のみのラベル（赤）、B のみのラベル（緑）、個数差異（黄）を分類
3. `coordinate_tolerance` 範囲内の座標一致を「同一ラベル」と判定（座標比較オプション時）
4. 座標近傍で名称が変わったラベルペアを抽出（ラベル変更抽出オプション時）
5. プレフィックス一致ラベルを `unchanged_labels.xlsx` として別出力

---

## Excel 出力仕様

### 差分比較 Excel（`diff_labels.xlsx`）

| シート | 内容 |
|--------|------|
| `Summary` | 全ペアの概要（ファイル名・A/B ラベル数・差分数） |
| `<ペア名>` | ペアごとの差分詳細 |

**色分け規則:**

| 色 | 意味 |
|-----|------|
| 赤 | A ファイルにのみ存在 |
| 緑 | B ファイルにのみ存在 |
| 黄 | 両方に存在するが個数が異なる |

### 未変更ラベル Excel（`unchanged_labels.xlsx`）

`detect_label_changes` かつ `unchanged_prefixes` 指定時に生成。
プレフィックスに一致し変更がないラベルを列挙。

---

## オプション仕様

| オプション | 説明 |
|-----------|------|
| 機器符号のみ抽出 | DXF-extract-labels と同一の正規表現フィルタ |
| 機器符号妥当性チェック | 非適合機器符号を Invalid シートに出力 |
| 座標も含めて比較 | ラベル文字列 + 座標の組み合わせで一致判定 |
| 座標比較精度 | 許容誤差（デフォルト 0.01、min 0.0001、max 1.0） |
| ラベル変更ペアを抽出 | 座標近傍のラベル名称変更候補を抽出 |
| 未変更ラベル用プレフィックス | config.txt から読み込み、UI で編集可 |

---

## config.txt

```
# 例（改行区切りプレフィックス）
CB
ELB
MCCB
```

- アプリ起動時に `load_default_prefixes()` で読み込む
- UI 上の `st.text_area` で一時的に上書き可能（セッション内のみ有効）
- config.txt を直接編集するとデフォルト値が変わる

---

## セッション状態

| キー | 型 | 内容 |
|------|-----|------|
| `file_pairs` | list[dict] | 5 ペア分のファイルオブジェクトとペア名 |
| `excel_result` | bytes | 差分 Excel バイナリ |
| `unchanged_excel_result` | bytes\|None | 未変更ラベル Excel バイナリ |
| `output_filename` | str | ダウンロードファイル名 |
| `processing_settings` | dict | 適用したオプション設定 |
| `prefix_text_input` | str | テキストエリアのプレフィックス内容 |

---

## 依存パッケージ

```
streamlit>=1.40.0, ezdxf>=1.4.2, pandas>=2.0.0
xlsxwriter>=3.0.0, openpyxl>=3.0.0
```

---

## 共有モジュール

`utils/extract_labels.py` と `utils/common_utils.py` は以下のプロジェクトと同一ロジックを持つ:
- DXF-extract-labels
- DXF-diff-processor
- DXF-tools
- DXF-tools-for-admin

いずれかを修正する場合は他プロジェクトへの伝播を確認すること。

---

## 既知の制限

| 制限 | 詳細 |
|------|------|
| 最大 5 ペア | ハードコード。変更は app.py の `range(5)` と session_state 初期化を修正 |
| 座標比較の精度 | DXF 座標系の単位に依存するため、ファイルによって適切な精度値が異なる |
| 未変更ラベルは今回セッションのみ | config.txt は変更されない |

---

## 機能拡張ポイント

| テーマ | 実装アプローチ |
|--------|--------------|
| ペア数の動的追加 | `st.button("ペアを追加")` でリストを動的拡張 |
| ペア名の自動生成 | A/B ファイル名から共通プレフィックスを抽出 |
| 差分ハイライト DXF 出力 | DXF-diff-processor のパイプラインと連携 |
| config.txt の UI 編集 & 保存 | `st.text_area` + `st.button("保存")` で config.txt を上書き |
| 複数シート入力 | 現在は DXF のみ対応。Excel や CSV のラベルリストとの比較を追加可能 |
