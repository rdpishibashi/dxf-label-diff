import pandas as pd
import io
from collections import Counter
import os
import sys

# 共通ユーティリティをインポート
from .common_utils import process_circuit_symbol_labels
from .extract_labels import extract_labels
from .coordinate_comparison import (
    round_labels_with_coordinates,
    aggregate_by_label,
    create_data_rows_from_summary,
    group_labels_by_coordinate,
    find_label_change_pairs,
    build_label_change_rows
)


def compare_labels_multi(file_pairs, filter_non_parts=False, sort_order="asc", validate_ref_designators=False,
                         compare_with_coordinates=False, coordinate_tolerance=0.01, detect_label_changes=False,
                         unchanged_prefixes=None, return_unchanged=False):
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
        compare_with_coordinates: 座標も含めて比較するかどうか
        coordinate_tolerance: 座標比較の許容誤差（デフォルト: 0.01）
        detect_label_changes: 座標に基づいてラベル変更ペアを抽出するかどうか
        unchanged_prefixes: 未変更ラベル抽出用のプレフィックスリスト
        return_unchanged: True の場合、未変更ラベルのExcelも併せて返す

    Returns:
        bytes または tuple: return_unchanged=True の場合 (比較Excel, 未変更Excel)、
            それ以外は比較Excelのみ
    """
    # Excelファイルを作成するためのライターオブジェクト
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    unchanged_prefixes = [p for p in (unchanged_prefixes or []) if p]
    collect_unchanged = bool(detect_label_changes and unchanged_prefixes and return_unchanged)
    unchanged_results = {prefix: [] for prefix in unchanged_prefixes} if collect_unchanged else {}

    # 各ペアを処理
    for idx, (file_a, file_b, temp_file_a, temp_file_b, pair_name) in enumerate(file_pairs):
        needs_coordinates = compare_with_coordinates or detect_label_changes

        # ラベルを抽出（extract_labelsを再利用）- 一時ファイルパスを使用
        labels_a_data, info_a = extract_labels(
            temp_file_a,
            filter_non_parts=filter_non_parts,
            sort_order=sort_order,
            validate_ref_designators=validate_ref_designators,
            include_coordinates=needs_coordinates
        )
        labels_b_data, info_b = extract_labels(
            temp_file_b,
            filter_non_parts=filter_non_parts,
            sort_order=sort_order,
            validate_ref_designators=validate_ref_designators,
            include_coordinates=needs_coordinates
        )

        labels_a_coords = labels_a_data if needs_coordinates else None
        labels_b_coords = labels_b_data if needs_coordinates else None

        if compare_with_coordinates:
            labels_a = labels_a_coords
            labels_b = labels_b_coords
        else:
            if needs_coordinates:
                labels_a = [label for label, _, _ in labels_a_coords]
                labels_b = [label for label, _, _ in labels_b_coords]
            else:
                labels_a = labels_a_data
                labels_b = labels_b_data
        
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

        rounded_labels_a = rounded_labels_b = None
        label_summary = None
        if needs_coordinates:
            rounded_labels_a = round_labels_with_coordinates(labels_a_coords, coordinate_tolerance)
            rounded_labels_b = round_labels_with_coordinates(labels_b_coords, coordinate_tolerance)
            counter_a_with_coords = Counter(rounded_labels_a)
            counter_b_with_coords = Counter(rounded_labels_b)
            label_summary = aggregate_by_label(counter_a_with_coords, counter_b_with_coords)
        label_change_rows = []
        if detect_label_changes and needs_coordinates:
            grouped_a = group_labels_by_coordinate(rounded_labels_a)
            grouped_b = group_labels_by_coordinate(rounded_labels_b)
            change_pairs = find_label_change_pairs(grouped_a, grouped_b)
            label_change_rows = build_label_change_rows(change_pairs)

        if collect_unchanged and label_summary:
            unchanged_counts = {
                label: summary['common']
                for label, summary in label_summary.items()
                if summary['a_only'] == 0 and summary['b_only'] == 0 and summary['common'] > 0
            }
            if unchanged_counts:
                for prefix in unchanged_prefixes:
                    matching = [
                        {
                            'Pair': sheet_name,
                            'Label': label,
                            'Count': count
                        }
                        for label, count in unchanged_counts.items()
                        if label.startswith(prefix)
                    ]
                    if matching:
                        unchanged_results[prefix].extend(sorted(matching, key=lambda x: x['Label']))

        # 座標比較モードと従来モードで処理を分岐
        if compare_with_coordinates:
            # 座標比較モード：(ラベル, X, Y)のタプルをキーとして比較
            # Use coordinate_comparison utilities
            # Create data rows using utility function
            data_rows = create_data_rows_from_summary(label_summary)

            # Map column names to match Excel output format
            for row in data_rows:
                row['Label'] = row.pop('label')
                row[file_a_name] = row.pop('count_a')
                row[file_b_name] = row.pop('count_b')
                row['Status'] = row.pop('status')
                row['Diff (B-A)'] = row.pop('diff')

            # データフレームを作成
            df = pd.DataFrame(data_rows)

        else:
            # 従来モード：ラベルの出現回数をカウント
            counter_a = Counter(labels_a)
            counter_b = Counter(labels_b)

            # すべてのユニークなラベルを取得
            all_labels = sorted(set(list(counter_a.keys()) + list(counter_b.keys())))

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

        # ラベル変更ペアのシートを追加
        if detect_label_changes:
            change_sheet_name = f"{sheet_name}_Changes"[:31]
            change_columns = ['Coordinate X', 'Coordinate Y', 'Label A', 'Label B']
            if label_change_rows:
                change_df = pd.DataFrame(label_change_rows)
                change_df = change_df.sort_values(['Label A', 'Label B']).reset_index(drop=True)
            else:
                change_df = pd.DataFrame(columns=change_columns)

            change_df.to_excel(writer, sheet_name=change_sheet_name, index=False)
            change_worksheet = writer.sheets[change_sheet_name]
            change_worksheet.set_column('A:B', 12)
            change_worksheet.set_column('C:D', 20)

            for col_num, value in enumerate(change_df.columns.values):
                change_worksheet.write(0, col_num, value, format_header)
            change_worksheet.freeze_panes(1, 0)
        
    # Excelファイルを保存
    writer.close()
    output.seek(0)
    main_excel = output.getvalue()

    unchanged_output = None
    if collect_unchanged:
        unchanged_output = io.BytesIO()
        unchanged_writer = pd.ExcelWriter(unchanged_output, engine='xlsxwriter')
        for prefix in unchanged_prefixes:
            rows = unchanged_results.get(prefix, [])
            if rows:
                df = pd.DataFrame(rows).sort_values(['Label', 'Pair']).reset_index(drop=True)
            else:
                df = pd.DataFrame(columns=['Pair', 'Label', 'Count'])
            sheet_name = prefix[:31]
            if not sheet_name:
                sheet_name = "Prefix"
            df.to_excel(unchanged_writer, sheet_name=sheet_name, index=False)
            worksheet = unchanged_writer.sheets[sheet_name]
            worksheet.set_column('A:A', 20)
            worksheet.set_column('B:B', 30)
            worksheet.set_column('C:C', 10)
        unchanged_writer.close()
        unchanged_output.seek(0)
        unchanged_output = unchanged_output.getvalue()
    
    if return_unchanged:
        return main_excel, unchanged_output
    return main_excel
