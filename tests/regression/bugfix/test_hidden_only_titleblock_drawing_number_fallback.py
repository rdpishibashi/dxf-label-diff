"""
このテストが守るもの: extract_labels() が、唯一の図番を持つタイトルブロック
（INSERT）がoff/frozenレイヤーに置かれている図面でも、図番を正しく抽出でき
ること。ただし出力ラベル自体は常に表示中のエンティティのみに限定される
（非表示タイトルブロックの文字は出力に混入しない）こと。

不具合の識別子: 2026-09-23 ユーザー報告（DXF-extract-labelsで発覚）
    2026-09-16のレイヤー単位off/frozen判定追加（本プロジェクトでは
    `test_off_frozen_layer_titleblock_excluded.py` が固定）により、
    唯一のタイトルブロックがoff/frozenレイヤーに置かれている図面
    （実データ EE5322-455-02A.dxf/EE5322-455-18A.dxf）で、図番の手がかりが
    一切残らず `main_drawing_number` が常に None になっていた。

以前どう壊れていたか:
    is_invisible() がレイヤー単位でエンティティを除外する際、除外対象が
    「他に候補がある中の余剰（旧タイトルブロック等）」であることを前提と
    しており、「唯一の候補がたまたま非表示レイヤーに置かれている」ケースを
    考慮していなかった。表示中のエンティティだけで図番候補が0件になる。

修正後に保証したいこと:
    - 表示中のエンティティだけでは図番候補が1件も見つからない場合に限り、
      レイヤーoff/frozenを無視した（entity自身のinvisible属性のみの）
      フォールバック探索で図番を発見する。
    - 出力ラベル（extract_labels()の戻り値labels）は、フォールバック発動時
      でも常に表示中のエンティティのみを対象にする——非表示タイトルブロック
      の文字はフォールバック発動時も出力ラベルに一切混入しない。
    - 表示中のタイトルブロックが既にある通常の図面では、フォールバックは
      発動せず従来通りの結果になる。

実行:
    cd DXF-label-diff
    python -m pytest tests/regression/bugfix/test_hidden_only_titleblock_drawing_number_fallback.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import ezdxf

from utils.extract_labels import extract_labels


def _save(doc):
    with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as f:
        path = f.name
    doc.saveas(path)
    return path


def _build_doc_with_only_hidden_titleblock():
    """唯一のタイトルブロック（図番 'EE9999-001-01A' を持つINSERT）が
    off+frozenレイヤーに置かれている図面。タイトルブロック外に可視ラベル
    'R10' を1つ配置する。"""
    doc = ezdxf.new()
    msp = doc.modelspace()

    block = doc.blocks.new(name='TITLEBLOCK')
    block.add_text('EE9999-001-01A', dxfattribs={'insert': (170, 25)})
    block.add_text('TITLE', dxfattribs={'insert': (100, 50)})

    hidden_layer_name = 'OLD_TITLEBLOCK_LAYER'
    doc.layers.add(hidden_layer_name)
    hidden_layer = doc.layers.get(hidden_layer_name)
    hidden_layer.off()
    hidden_layer.freeze()

    msp.add_blockref('TITLEBLOCK', (0, 0), dxfattribs={'layer': hidden_layer_name})
    msp.add_text('R10', dxfattribs={'insert': (10, 10)})
    return doc


def _build_doc_with_visible_and_hidden_titleblock():
    """可視のタイトルブロック（図番 'EE1111-001-01A'）と、別座標に置かれた
    非表示のタイトルブロック（図番 'EE9999-001-01A'）を持つ図面。表示中の
    図番が既に見つかるため、フォールバックは発動しない。"""
    doc = ezdxf.new()
    msp = doc.modelspace()

    visible_block = doc.blocks.new(name='VISIBLE_TB')
    visible_block.add_text('EE1111-001-01A', dxfattribs={'insert': (170, 25)})
    msp.add_blockref('VISIBLE_TB', (0, 0))

    hidden_block = doc.blocks.new(name='HIDDEN_TB')
    hidden_block.add_text('EE9999-001-01A', dxfattribs={'insert': (170, 25)})
    hidden_layer_name = 'OLD_TITLEBLOCK_LAYER'
    doc.layers.add(hidden_layer_name)
    hidden_layer = doc.layers.get(hidden_layer_name)
    hidden_layer.off()
    hidden_layer.freeze()
    msp.add_blockref('HIDDEN_TB', (1000, 0), dxfattribs={'layer': hidden_layer_name})
    return doc


def test_drawing_number_recovered_via_fallback_when_only_titleblock_is_hidden():
    path = _save(_build_doc_with_only_hidden_titleblock())
    try:
        labels, info = extract_labels(path, extract_drawing_numbers_option=True)
    finally:
        os.remove(path)
    assert info['main_drawing_number'] == 'EE9999-001-01A'


def test_output_labels_still_exclude_hidden_titleblock_text():
    path = _save(_build_doc_with_only_hidden_titleblock())
    try:
        labels, info = extract_labels(path, extract_drawing_numbers_option=True)
    finally:
        os.remove(path)
    assert 'R10' in labels
    assert 'EE9999-001-01A' not in labels
    assert 'TITLE' not in labels


def test_visible_titleblock_takes_precedence_fallback_not_triggered():
    path = _save(_build_doc_with_visible_and_hidden_titleblock())
    try:
        labels, info = extract_labels(path, extract_drawing_numbers_option=True)
    finally:
        os.remove(path)
    assert info['main_drawing_number'] == 'EE1111-001-01A'
    assert 'EE9999-001-01A' not in info['all_drawing_numbers']
