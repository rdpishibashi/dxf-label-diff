import pandas as pd
import io
from collections import Counter
import os
import sys

# 共通ユーティリティをインポート
from .common_utils import process_circuit_symbol_labels
from .extract_labels import extract_labels

def compare_labels_multi(file_pairs, filter_non_parts=False, sort_order="asc", validate_ref_designators=False):
    """
    複数のDXFファイルペアのラベル比較結果をExcelとして出力する
    
    Args:
        file_pairs: ファイルペアのリスト[(file_a, file_b, temp_file_a, temp_file_b, pair_name), ...]
          - file_a, file_b: 元のアップロードファイルオブジェクト
          - temp_file_a, temp_file_b: 一時ファイルのパス
          - pair_name: ペア名
        filter_non_parts: 回路記号（候補）のみを抽出するかどうか
        sort_order: ソート順（"asc"=昇順, "desc"=降順, "none"=ソートなし）
        validate_ref_designators: 回路記号の妥当性をチェックするかどうか
        
    Returns:
        bytes: 生成されたExcelファイルのバイナリデータ
    """
    # Excelファイルを作成するためのライターオブジェクト
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    # サマリーデータを格納するリスト
    summary_data = []
    
    # 各ペアを処理
    for idx, (file_a, file_b, temp_file_a, temp_file_b, pair_name) in enumerate(file_pairs):
        # ラベルを抽出（extract_labelsを再利用）- 一時ファイルパスを使用
        labels_a, info_a = extract_labels(
            temp_file_a, 
            filter_non_parts=filter_non_parts, 
            sort_order=sort_order,
            validate_ref_designators=validate_ref_designators
        )
        labels_b, info_b = extract_labels(
            temp_file_b, 
            filter_non_parts=filter_non_parts, 
            sort_order=sort_order,
            validate_ref_designators=validate_ref_designators
        )
        
        # ラベルの出現回数をカウント
        counter_a = Counter(labels_a)
        counter_b = Counter(labels_b)
        
        # すべてのユニークなラベルを取得
        all_labels = sorted(set(list(counter_a.keys()) + list(counter_b.keys())))
        
        # 元のアップロードファイル名を使用（UploadedFileオブジェクトから）
        file_a_base = os.path.splitext(file_a.name)[0]
        file_b_base = os.path.splitext(file_b.name)[0]
        file_a_name = f"A:{file_a_base}"
        file_b_name = f"B:{file_b_base}"
        
        # シート名を決定（最大31文字）
        if pair_name:
            # カスタム名がある場合
            sheet_name = f"{pair_name}"[:31]
        else:
            # ファイル名からシート名を生成
            sheet_name = f"Pair{idx+1}"[:31]
            
        # データフレームの作成
        df = pd.DataFrame({
            'Label': all_labels,
            file_a_name: [counter_a.get(label, 0) for label in all_labels],
            file_b_name: [counter_b.get(label, 0) for label in all_labels]
        })
        
        # ラベルがファイルAにのみ存在する（Aのみ）、ファイルBにのみ存在する（Bのみ）、
        # または両方に存在するが異なる回数（差異あり）、完全に一致（完全一致）を示す列を追加
        df['Status'] = df.apply(lambda row: 
            'A Only' if row[file_a_name] > 0 and row[file_b_name] == 0 else
            'B Only' if row[file_a_name] == 0 and row[file_b_name] > 0 else
            'Different' if row[file_a_name] != row[file_b_name] else
            'Same', axis=1)
        
        # 差分情報の列を追加（B - A）
        df['Diff (B-A)'] = df[file_b_name] - df[file_a_name]
        
        # データフレームをExcelシートに出力
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # ワークシートとワークブックのオブジェクトを取得
        worksheet = writer.sheets[sheet_name]
        workbook = writer.book
        
        # セルの書式設定
        format_header = workbook.add_format({
            'bold': True, 
            'text_wrap': True, 
            'valign': 'top', 
            'border': 1,
            'bg_color': '#D9E1F2'
        })
        
        format_a_only = workbook.add_format({'bg_color': '#FFC7CE'})  # 淡い赤
        format_b_only = workbook.add_format({'bg_color': '#C6EFCE'})  # 淡い緑
        format_different = workbook.add_format({'bg_color': '#FFEB9C'})  # 淡い黄
        
        # 列の幅を調整
        worksheet.set_column('A:A', 25)  # ラベル列
        worksheet.set_column('B:C', 15)  # ファイル列
        worksheet.set_column('D:D', 15)  # ステータス列
        worksheet.set_column('E:E', 10)  # 差分列
        
        # ヘッダー行の書式を設定
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, format_header)
        
        # 条件付き書式の適用
        # 'Status'列が'A Only'の場合、行全体を淡い赤で表示
        # 'Status'列が'B Only'の場合、行全体を淡い緑で表示
        # 'Status'列が'Different'の場合、行全体を淡い黄で表示
        worksheet.conditional_format(1, 0, len(df), len(df.columns)-1, {
            'type': 'formula',
            'criteria': '=$D2="A Only"',
            'format': format_a_only
        })
        
        worksheet.conditional_format(1, 0, len(df), len(df.columns)-1, {
            'type': 'formula',
            'criteria': '=$D2="B Only"',
            'format': format_b_only
        })
        
        worksheet.conditional_format(1, 0, len(df), len(df.columns)-1, {
            'type': 'formula',
            'criteria': '=$D2="Different"',
            'format': format_different
        })
        
        # ヘッダー行を固定
        worksheet.freeze_panes(1, 0)
        
        # 回路記号妥当性チェック結果がある場合、別シートに追加
        if validate_ref_designators and filter_non_parts:
            invalid_a = info_a.get('invalid_ref_designators', [])
            invalid_b = info_b.get('invalid_ref_designators', [])
            
            if invalid_a or invalid_b:
                # 妥当性チェック結果シート名
                validation_sheet_name = f"{sheet_name}_Invalid"[:31]
                
                # 適合しない回路記号をまとめる
                max_len = max(len(invalid_a), len(invalid_b))
                invalid_a_padded = invalid_a + [''] * (max_len - len(invalid_a))
                invalid_b_padded = invalid_b + [''] * (max_len - len(invalid_b))
                
                validation_df = pd.DataFrame({
                    f'Invalid in {file_a_base}': invalid_a_padded,
                    f'Invalid in {file_b_base}': invalid_b_padded
                })
                
                validation_df.to_excel(writer, sheet_name=validation_sheet_name, index=False)
                
                # 妥当性チェック結果シートのフォーマット
                validation_worksheet = writer.sheets[validation_sheet_name]
                validation_worksheet.set_column('A:B', 30)
                
                # ヘッダー行の書式を設定
                for col_num, value in enumerate(validation_df.columns.values):
                    validation_worksheet.write(0, col_num, value, format_header)
        
        # 個別シートにサマリー情報を追加
        sheet_summary = [
            [f"ファイルA: {file_a_name}", f"ラベル総数: {len(labels_a)}", f"ユニークラベル数: {len(counter_a)}"],
            [f"ファイルB: {file_b_name}", f"ラベル総数: {len(labels_b)}", f"ユニークラベル数: {len(counter_b)}"],
            ["", "", ""],
            ["差分サマリー:", "", ""],
            [f"Aのみのラベル: {sum(1 for s in df['Status'] if s == 'A Only')}", 
             f"Bのみのラベル: {sum(1 for s in df['Status'] if s == 'B Only')}", 
             f"異なる個数のラベル: {sum(1 for s in df['Status'] if s == 'Different')}"]
        ]
        
        # サマリーデータを収集
        invalid_a_count = len(info_a.get('invalid_ref_designators', [])) if validate_ref_designators and filter_non_parts else 0
        invalid_b_count = len(info_b.get('invalid_ref_designators', [])) if validate_ref_designators and filter_non_parts else 0
        
        summary_info = {
            'sheet_name': sheet_name,
            'file_a_base': file_a_base,
            'file_b_base': file_b_base,
            'a_only_count': sum(1 for s in df['Status'] if s == 'A Only'),
            'b_only_count': sum(1 for s in df['Status'] if s == 'B Only'),
            'different_count': sum(1 for s in df['Status'] if s == 'Different'),
            'total_labels': len(all_labels),
            'invalid_a_count': invalid_a_count,
            'invalid_b_count': invalid_b_count
        }
        summary_data.append(summary_info)
    
    # サマリーシートを最後に作成
    workbook = writer.book
    summary_sheet = workbook.add_worksheet("Summary")
    writer.sheets["Summary"] = summary_sheet
    
    # サマリーシートのタイトル
    title_format = workbook.add_format({
        'bold': True,
        'font_size': 14,
        'align': 'center',
        'valign': 'vcenter'
    })
    summary_sheet.merge_range('A1:C1', 'ラベル差分比較サマリー', title_format)
    
    # ヘッダー行を作成
    summary_row = 2
    pair_header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white'
    })
    summary_sheet.write(summary_row, 0, "シート名", pair_header_format)
    summary_sheet.write(summary_row, 1, "ファイルA", pair_header_format)
    summary_sheet.write(summary_row, 2, "ファイルB", pair_header_format)
    summary_sheet.write(summary_row, 3, "Aのみ", pair_header_format)
    summary_sheet.write(summary_row, 4, "Bのみ", pair_header_format)
    summary_sheet.write(summary_row, 5, "異なる個数", pair_header_format)
    summary_sheet.write(summary_row, 6, "ラベル総数", pair_header_format)
    
    # 妥当性チェックが有効な場合は追加の列
    if validate_ref_designators and filter_non_parts:
        summary_sheet.write(summary_row, 7, "適合しないA", pair_header_format)
        summary_sheet.write(summary_row, 8, "適合しないB", pair_header_format)
    
    summary_row += 1
    
    # 各ペアの情報を追加
    for idx, info in enumerate(summary_data):
        summary_sheet.write(idx + 3, 0, info['sheet_name'])
        summary_sheet.write(idx + 3, 1, info['file_a_base'])
        summary_sheet.write(idx + 3, 2, info['file_b_base'])
        summary_sheet.write(idx + 3, 3, info['a_only_count'])
        summary_sheet.write(idx + 3, 4, info['b_only_count'])
        summary_sheet.write(idx + 3, 5, info['different_count'])
        summary_sheet.write(idx + 3, 6, info['total_labels'])
        
        # 妥当性チェック結果をサマリーに追加
        if validate_ref_designators and filter_non_parts:
            summary_sheet.write(idx + 3, 7, info['invalid_a_count'])
            summary_sheet.write(idx + 3, 8, info['invalid_b_count'])
    
    # 列幅を調整
    summary_sheet.set_column('A:A', 15)  # シート名
    summary_sheet.set_column('B:C', 20)  # ファイル名
    summary_sheet.set_column('D:I', 12)  # 数値列
    
    # Excelファイルを保存
    writer.close()
    output.seek(0)
    
    return output.getvalue()