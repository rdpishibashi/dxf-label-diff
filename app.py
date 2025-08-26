import streamlit as st
import os
import tempfile
import sys
from pathlib import Path

# utils モジュールをインポート可能にするためのパスの追加
current_dir = os.path.dirname(os.path.abspath(__file__))
utils_path = os.path.join(current_dir, 'utils')
sys.path.insert(0, utils_path)

from utils.compare_labels import compare_labels_multi
from utils.common_utils import save_uploadedfile, handle_error

st.set_page_config(
    page_title="DXF Label Diff",
    page_icon="📝",
    layout="wide",
)

def generate_output_filename(file_pairs):
    """
    出力ファイル名を生成: 固定ファイル名を返す
    """
    return "diff_labels.xlsx"

def app():
    st.title('DXF Label Diff')
    st.write('複数のDXFファイルペアのラベルを比較し、差分をExcel形式で出力します。')
    
    # プログラム説明
    with st.expander("ℹ️ プログラム説明", expanded=False):
        help_text = [
            "このツールは、複数のDXFファイルペアからテキスト要素（ラベル）を抽出し、各ペアごとに比較結果をExcelファイルに出力します。",
            "",
            "**使用手順：**",
            "1. 各ファイルペアを登録してください（最大5ペア）",
            "2. 必要に応じてオプション設定を調整します",
            "3. 「ラベル差分を比較」ボタンをクリックして処理を実行します",
            "",
            "**Excelファイルの内容：**",
            "- 各ペアごとに個別のシートを作成",
            "- サマリーシートで全体の比較結果を表示",
            "- 各シートでは、ファイルAのみ、ファイルBのみ、両方に存在するが数が異なるラベルを色分けして表示",
            "",
            "**高度な機能：**",
            "- 機器符号（回路記号）のみを抽出するフィルタリング",
            "- 機器符号の妥当性チェック（標準フォーマットとの適合性）",
            "- ラベルの並び替え（昇順、降順、並び替えなし）"
        ]
        
        st.info("\n".join(help_text))
    
    # ファイルペア登録UI
    st.subheader("ファイルペア登録")
    st.write("最大5ペアのDXFファイルを登録できます")
    
    # セッション状態の初期化
    if 'file_pairs' not in st.session_state:
        st.session_state.file_pairs = []
        for i in range(5):  # 最大5ペア
            st.session_state.file_pairs.append({
                'fileA': None,
                'fileB': None,
                'name': f"Pair{i+1}"
            })
    
    # 各ペアの入力フォーム
    file_pairs_valid = []
    
    for i in range(5):  # 最大5ペア
        with st.expander(f"ファイルペア {i+1}", expanded=i==0):
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                uploaded_file_a = st.file_uploader(
                    f"DXFファイルA {i+1}", 
                    type="dxf", 
                    key=f"label_a_{i}"
                )
                if uploaded_file_a:
                    st.session_state.file_pairs[i]['fileA'] = uploaded_file_a
                
            with col2:
                uploaded_file_b = st.file_uploader(
                    f"DXFファイルB {i+1}", 
                    type="dxf", 
                    key=f"label_b_{i}"
                )
                if uploaded_file_b:
                    st.session_state.file_pairs[i]['fileB'] = uploaded_file_b
            
            with col3:
                pair_name = st.text_input(
                    "ペア名",
                    value=st.session_state.file_pairs[i]['name'],
                    key=f"pair_name_{i}"
                )
                st.session_state.file_pairs[i]['name'] = pair_name
            
            # 両方のファイルが選択されている場合、有効なペアとして追加
            if st.session_state.file_pairs[i]['fileA'] and st.session_state.file_pairs[i]['fileB']:
                file_pairs_valid.append((
                    st.session_state.file_pairs[i]['fileA'],
                    st.session_state.file_pairs[i]['fileB'],
                    st.session_state.file_pairs[i]['name']
                ))
                
                # プレビュー表示
                st.success(f"Pair{i+1}: {st.session_state.file_pairs[i]['fileA'].name} と {st.session_state.file_pairs[i]['fileB'].name} を比較")
    
    # オプション設定
    with st.expander("オプション設定", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            filter_option = st.checkbox(
                "機器符号（候補）のみ抽出", 
                value=False, 
                help="以下のパターンに一致するラベルのみを機器符号として抽出します："
                     "\n\n【基本パターン】"
                     "\n• 英文字のみ: CNCNT, FB"
                     "\n• 英文字+数字: R10, CN3, PSW1"  
                     "\n• 英文字+数字+英文字: X14A, RMSS2A"
                     "\n\n【括弧付きパターン】"
                     "\n• 英文字(補足): FB(), MSS(MOTOR)"
                     "\n• 英文字+数字(補足): R10(2.2K), MSSA(+)"
                     "\n• 英文字+数字+英文字(補足): U23B(DAC)"
                     "\n\n※英文字だけの場合は英文字2個以上、それ以外の場合は英文字1個以上、数字1個以上必要です"
            )
            
            # 機器符号妥当性チェックオプション（機器符号フィルタリングが有効な場合のみ表示）
            validate_ref_designators = False
            if filter_option:
                validate_ref_designators = st.checkbox(
                    "機器符号妥当性チェック", 
                    value=False,
                    help="抽出された機器符号がフォーマットに適合するかチェックします。"
                         "\n適合しない機器符号のリストを別シートに出力します。"
                         "\n（例：CBnnn, ELB(CB) nnn, R, Annn等の標準フォーマット）"
                )
        
        with col2:
            sort_option = st.selectbox(
                "並び替え", 
                options=[
                    ("昇順", "asc"), 
                    ("逆順", "desc"),
                    ("並び替えなし", "none")
                ],
                format_func=lambda x: x[0],
                help="ラベルの並び替え順を指定します",
                index=0  # デフォルトで昇順を選択
            )
            sort_value = sort_option[1]  # タプルの2番目の要素（実際の値）を取得
            
            # 出力ファイル名設定
            output_filename = st.text_input(
                "出力Excelファイル名", 
                value="diff_labels.xlsx",
                help="出力するExcelファイルの名前を指定します"
            )
            if not output_filename.endswith('.xlsx'):
                output_filename += '.xlsx'
    
    if file_pairs_valid:
        try:
            # ファイルが選択されたら処理ボタンを表示
            if st.button("ラベル差分を比較", disabled=len(file_pairs_valid) == 0):
                # 全てのファイルを一時ディレクトリに保存
                with st.spinner(f'{len(file_pairs_valid)}ペアのDXFファイルを処理中...'):
                    temp_file_pairs = []
                    temp_files_to_cleanup = []
                    
                    for file_a, file_b, pair_name in file_pairs_valid:
                        temp_file_a = save_uploadedfile(file_a)
                        temp_file_b = save_uploadedfile(file_b)
                        temp_file_pairs.append((file_a, file_b, temp_file_a, temp_file_b, pair_name))
                        temp_files_to_cleanup.extend([temp_file_a, temp_file_b])
                    
                    # Excel出力を生成
                    excel_data = compare_labels_multi(
                        temp_file_pairs,
                        filter_non_parts=filter_option,
                        sort_order=sort_value,
                        validate_ref_designators=validate_ref_designators
                    )
                    
                    # 結果をセッション状態に保存
                    st.session_state.excel_result = excel_data
                    st.session_state.output_filename = output_filename
                    st.session_state.processing_settings = {
                        'filter_option': filter_option,
                        'validate_ref_designators': validate_ref_designators,
                        'sort_order': sort_value
                    }
                    
                # 一時ファイルの削除
                for temp_file in temp_files_to_cleanup:
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
        
        except Exception as e:
            handle_error(e)
        
        # セッション状態に保存された結果を表示
        if 'excel_result' in st.session_state and st.session_state.excel_result:
            settings = st.session_state.get('processing_settings', {})
            
            # 結果サマリーの表示
            st.success(f"全{len(file_pairs_valid)}ペアのDXFラベル比較が完了しました")
            
            # 処理オプションの情報を表示
            option_info = []
            if settings.get('filter_option'):
                option_info.append("機器符号フィルタリング: 有効")
                if settings.get('validate_ref_designators'):
                    option_info.append("機器符号妥当性チェック: 有効")
            sort_labels = {'asc': '昇順', 'desc': '降順', 'none': 'なし'}
            option_info.append(f"並び替え: {sort_labels.get(settings.get('sort_order', 'asc'))}")
            
            if option_info:
                st.info("処理オプション: " + " | ".join(option_info))
            
            # ダウンロードボタンの表示
            st.subheader("📥 結果のダウンロード")
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**出力ファイル**: {st.session_state.output_filename}")
            
            with col2:
                st.download_button(
                    label="Excelをダウンロード",
                    data=st.session_state.excel_result,
                    file_name=st.session_state.output_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            # 新しい比較を開始するボタン
            if st.button("🔄 新しい比較を開始", key="restart_button"):
                # セッション状態をクリアして新しい比較を開始
                for key in ['excel_result', 'output_filename', 'processing_settings']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
    else:
        st.warning("少なくとも1つのファイルペア（DXFファイルA、DXFファイルB）を登録してください。")

if __name__ == "__main__":
    app()