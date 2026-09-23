import os
import tempfile
import traceback
import re

def is_invisible(e, check_layer=True):
    """DXFの`invisible`属性（グループコード60、1=非表示）が立っている
    エンティティ、または**エンティティが所属するレイヤーがオフ/フリーズ
    されている**エンティティかを返す。CADソフト上で「非表示」に設定された
    図形（紙面には一切表示されない）は、たとえDXFファイル中に座標・テキスト
    として存在していても収集対象にしてはならない（2026-09-16、DXF-extract-labels
    2026-09-11・2026-09-16の横展開に伴い、DXF-label-diffは`is_invisible()`
    自体が未実装だったため新設した。詳細はDXF-extract-labels/tests/regression/
    test_ref_designator.pyのinvisible関連テストを参照）。

    呼び出し側は次の3箇所すべてでチェックする必要がある（`virtual_entities()`
    は親INSERTのinvisible属性を継承しないため、INSERT自身のチェックを
    省くと、INSERT自身がinvisibleでも展開後の中身は素通りしてしまう）:
      1. 直接配置エンティティ
      2. INSERT自身（invisibleなINSERTは中身ごと丸ごと除外する）
      3. `virtual_entities()`で展開した仮想エンティティ（親が可視でも
         個々の子エンティティにinvisibleが立っている場合があるため）

    レイヤー単位の非表示状態: エンティティ自身の`invisible`属性が立って
    いなくても、そのエンティティが置かれたレイヤー自体が「オフ」または
    「フリーズ」されていれば、画面上・印刷時ともに一切表示されない。
    ULVAC標準の改版運用では、旧版のタイトルブロックをエンティティ単位の
    invisible属性ではなく、専用レイヤーごとオフ/フリーズして非表示にする
    例があり、この場合は上記の`invisible`属性チェックだけでは検出できない。
    `virtual_entities()`で展開した仮想エンティティも`.doc`経由で元の
    レイヤーテーブルを参照できるため、同じチェックで対応できる（`.layer`
    属性は展開後も元のレイヤー名を保持し、親INSERTのレイヤー状態を継承
    しない`invisible`属性とは異なる）。レイヤーテーブルに存在しない・
    `.doc`が取得できない等の異常系は「非表示ではない」側にフォールバック
    する（誤って全除外にならないよう保守的に扱う）。

    `check_layer=False`（2026-09-23、DXF-extract-labelsからの横展開追加）:
    レイヤー単位の判定をスキップし、エンティティ自身の`invisible`属性のみを
    見る。唯一のタイトルブロックがoff/frozenレイヤーに置かれている図面
    （`EE5322-455-02A.dxf`/`-18A.dxf`）で、図番の手がかりが表示中の
    エンティティだけでは1件も見つからない場合の**フォールバック探索**でのみ
    使う。既定の`True`では従来通りの判定を行う。
    """
    if bool(e.dxf.get('invisible', 0)):
        return True

    if not check_layer:
        return False

    layer_name = e.dxf.get('layer', None)
    doc = getattr(e, 'doc', None)
    if layer_name and doc is not None:
        try:
            if layer_name in doc.layers:
                layer = doc.layers.get(layer_name)
                if layer.is_off() or layer.is_frozen():
                    return True
        except Exception:
            pass

    return False


def save_uploadedfile(uploadedfile):
    """アップロードされたファイルを一時ディレクトリに保存する"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploadedfile.name)[1]) as f:
        f.write(uploadedfile.getbuffer())
        return f.name

def handle_error(e, show_traceback=True):
    """エラーを適切に処理して表示する"""
    import streamlit as st
    st.error(f"エラーが発生しました: {str(e)}")
    if show_traceback:
        st.error(traceback.format_exc())

def filter_non_circuit_symbols(labels, debug=False):
    """
    機器符号フォーマットに一致しないラベルをフィルタリングする
    
    新しい機器符号フォーマット:
    - AA+ (例: CNCNT, FB)
    - A+N+ (例: R10, CN3, PSW1)  
    - A+N+A+ (例: X14A, RMSS2A)
    - AA+([内容]) (例: FB(), MSS(MOTOR))
    - A+N+([内容]) (例: R10(2.2K), MSSA(+))
    - A+N+A+([内容]) (例: U23B(DAC))
    
    Args:
        labels: フィルタリング対象のラベルリスト
        debug: デバッグ情報を出力するかどうか
        
    Returns:
        tuple: (フィルタリング後のラベルリスト, 除外されたラベル数)
    """
    
    patterns = [
        # 英文字のみ（2文字以上）
        r'^[A-Za-z]{2,}$',
        
        # 英文字+数字
        r'^[A-Za-z]+\d+$',
        
        # 英文字+数字+英文字
        r'^[A-Za-z]+\d+[A-Za-z]+$',
        
        # 英文字のみ+括弧（オプション）
        r'^[A-Za-z]{2,}\([^)]*\)$',
        
        # 英文字+数字+括弧（オプション）
        r'^[A-Za-z]+\d+\([^)]*\)$',
        
        # 英文字+数字+英文字+括弧（オプション）
        r'^[A-Za-z]+\d+[A-Za-z]+\([^)]*\)$',
    ]
    
    filtered_labels = []
    excluded_count = 0
    
    for label in labels:
        is_match = False
        for pattern in patterns:
            if re.match(pattern, label):
                is_match = True
                break
        
        if is_match:
            filtered_labels.append(label)
            if debug:
                print(f"✓ 機器符号として認識: {label}")
        else:
            excluded_count += 1
            if debug:
                print(f"✗ 機器符号として除外: {label}")
    
    return filtered_labels, excluded_count

def validate_circuit_symbols(labels):
    """
    機器符号の妥当性をチェックし、適合しないものを返す
    
    Args:
        labels: チェック対象のラベルリスト
        
    Returns:
        list: 適合しない機器符号のリスト
    """
    # 標準的な機器符号パターンの定義
    standard_patterns = [
        # CB系（遮断器）
        r'^CB\d+$',                 # CB001, CB999
        r'^ELB\(CB\)\d+$',         # ELB(CB)001
        r'^MCCB\d+$',              # MCCB001
        r'^NFB\d+$',               # NFB001
        
        # 抵抗器
        r'^R\d*$',                 # R, R1, R10
        
        # コンデンサ
        r'^C\d*$',                 # C, C1, C10
        
        # インダクタ
        r'^L\d*$',                 # L, L1, L10
        
        # トランジスタ
        r'^Q\d*$',                 # Q, Q1, Q10
        
        # IC・集積回路
        r'^U\d*[A-Z]*$',           # U, U1, U10A
        
        # 電源関連
        r'^PSW?\d*$',              # PS, PSW, PS1, PSW1
        r'^DC\d*$',                # DC, DC1
        r'^AC\d*$',                # AC, AC1
        
        # モータ・機械系
        r'^M\d*[A-Z]*$',           # M, M1, M1A
        r'^MOT\d*$',               # MOT, MOT1
        
        # リレー・接触器
        r'^K\d*[A-Z]*$',           # K, K1, K1A
        r'^MC\d*$',                # MC, MC1
        
        # スイッチ・ボタン
        r'^S\d*[A-Z]*$',           # S, S1, S1A
        r'^SW\d*$',                # SW, SW1
        r'^PB\d*$',                # PB, PB1
        
        # 表示・ランプ
        r'^H\d*[A-Z]*$',           # H, H1, H1A
        r'^HL\d*$',                # HL, HL1
        r'^PL\d*$',                # PL, PL1
        
        # 端子・コネクタ
        r'^X\d*[A-Z]*$',           # X, X1, X14A
        r'^CN\d*$',                # CN, CN1
        r'^TB\d*$',                # TB, TB1
        
        # その他
        r'^F\d*$',                 # F, F1 (ヒューズ)
        r'^T\d*$',                 # T, T1 (変圧器)
        r'^A\d*$',                 # A, A1
    ]
    
    invalid_symbols = []
    
    for label in labels:
        is_valid = False
        for pattern in standard_patterns:
            if re.match(pattern, label):
                is_valid = True
                break
        
        if not is_valid:
            invalid_symbols.append(label)
    
    return invalid_symbols

def process_circuit_symbol_labels(labels, filter_non_parts=False, validate_ref_designators=False, debug=False):
    """
    ラベルに対して機器符号処理を統合的に実行する
    
    Args:
        labels: 処理対象のラベルリスト
        filter_non_parts: 機器符号以外のラベルをフィルタリングするかどうか
        validate_ref_designators: 機器符号の妥当性をチェックするかどうか
        debug: デバッグ情報を表示するかどうか
        
    Returns:
        dict: 処理結果を含む辞書
            - 'labels': 処理後のラベルリスト
            - 'filtered_count': フィルタリングで除外されたラベル数
            - 'invalid_ref_designators': 適合しない機器符号のリスト（妥当性チェック有効時のみ）
    """
    result = {
        'labels': labels.copy(),
        'filtered_count': 0,
        'invalid_ref_designators': []
    }
    
    # フィルタリング処理
    if filter_non_parts:
        filtered_labels, filtered_count = filter_non_circuit_symbols(labels, debug)
        result['labels'] = filtered_labels
        result['filtered_count'] = filtered_count
    
    # 機器符号妥当性チェック（フィルタリング後のラベルに対して実行）
    if validate_ref_designators and filter_non_parts:
        invalid_designators = validate_circuit_symbols(result['labels'])
        result['invalid_ref_designators'] = invalid_designators
    
    return result