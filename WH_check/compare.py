import json
import pandas as pd
from datetime import datetime
import re
import os
import sys
from dateutil import parser as date_parser
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl import load_workbook

def clean_text(text):
    """清理文本：去除所有空白字符、括号内容"""
    if not text or pd.isna(text):
        return ''
    text = str(text)
    # 去除所有空白字符（包括空格、换行、制表符等）
    text = re.sub(r'\s+', '', text)
    # 去除括号及其内容（包括中英文括号）
    text = re.sub(r'[（(][^）)]*[）)]', '', text)
    # 去除多余的标点符号
    text = text.replace('-', '').replace('，', ',').replace('。', '.')
    text = text.replace('、', ',').replace('；', ';').replace('：', ':')
    return text.strip()

def parse_date_input(date_str, default_year=2026):
    """解析用户输入的日期"""
    if not date_str or date_str.strip() == '':
        return None
    
    date_str = date_str.strip()
    
    # 处理简单格式如 "7.24" 或 "7/24"
    if re.match(r'^\d+[./-]\d+$', date_str):
        parts = re.split(r'[./-]', date_str)
        if len(parts) == 2:
            month = int(parts[0])
            day = int(parts[1])
            try:
                dt = datetime(default_year, month, day)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
    
    # 尝试用dateutil解析
    try:
        dt = date_parser.parse(date_str, fuzzy=True, default=datetime(default_year, 1, 1))
        if dt.year < 100:
            dt = dt.replace(year=default_year)
        return dt.strftime("%Y-%m-%d")
    except:
        pass
    
    print(f"⚠️  无法解析日期: '{date_str}'")
    return None

def get_date_range_from_user():
    """交互式获取日期范围"""
    print("\n" + "="*60)
    print("📅 请选择要对比的日期范围（默认年份为2026年）")
    print("="*60)
    print("支持格式示例：")
    print("  - 单日: 7.24 或 7/24")
    print("  - 范围: 7.22-7.26 或 07/22-07/26")
    print("  - 直接回车: 对比所有日期")
    print("  - 输入 'q' 退出")
    print("-"*60)
    
    while True:
        user_input = input("\n请输入日期: ").strip()
        
        if user_input.lower() in ['q', 'quit', 'exit']:
            print("已退出程序")
            sys.exit(0)
        
        if user_input == '':
            print("\n将对比所有日期（无日期过滤）")
            return None, None
        
        if '-' in user_input:
            parts = user_input.split('-')
            if len(parts) == 2:
                start_str = parts[0].strip()
                end_str = parts[1].strip()
                
                start_date = parse_date_input(start_str)
                end_date = parse_date_input(end_str)
                
                if start_date and end_date:
                    if start_date > end_date:
                        print(f"⚠️  起始日期 {start_date} 晚于结束日期 {end_date}，已自动交换")
                        start_date, end_date = end_date, start_date
                    print(f"\n✅ 已选择日期范围: {start_date} 至 {end_date}")
                    return start_date, end_date
                else:
                    print("❌ 日期格式无效，请重新输入")
                    continue
        
        single_date = parse_date_input(user_input)
        if single_date:
            print(f"\n✅ 已选择单日: {single_date}")
            return single_date, single_date
        else:
            print("❌ 日期格式无效，请重新输入")

def get_excel_sheets(excel_path):
    """获取Excel文件的所有子表名称"""
    try:
        xl = pd.ExcelFile(excel_path)
        return xl.sheet_names
    except Exception as e:
        print(f"❌ 读取Excel文件失败: {e}")
        return []

def select_sheet_interactive(sheets):
    """交互式选择子表"""
    # 自动选择PPG工业漆
    for sheet in sheets:
        if 'PPG工业漆' in sheet:
            return sheet
    
    print(f"\n📊 找到 {len(sheets)} 个子表，请选择：")
    for i, sheet in enumerate(sheets, 1):
        print(f"  {i}. {sheet}")
    
    while True:
        try:
            choice = input(f"\n请输入子表编号 (1-{len(sheets)}): ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(sheets):
                    return sheets[idx]
            print("❌ 无效选择，请重新输入")
        except:
            print("❌ 无效输入，请重新输入")

def apply_excel_highlighting(file_path):
    """给Excel文件中的差异单元格添加高亮"""
    try:
        wb = load_workbook(file_path)
        ws = wb.active
        
        # 定义颜色
        red_fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
        yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
        bold_font = Font(bold=True)
        red_font = Font(color="FF0000", bold=True)
        
        # 找到所有差异列（包含"差异_"的列）
        diff_cols = []
        for col in range(1, ws.max_column + 1):
            header = ws.cell(row=1, column=col).value
            if header and '差异_' in str(header):
                diff_cols.append(col)
        
        # 遍历所有差异列
        for col in diff_cols:
            for row in range(2, ws.max_row + 1):
                cell = ws.cell(row=row, column=col)
                if cell.value and '✗' in str(cell.value):
                    # 红色背景 + 白色加粗文字
                    cell.fill = red_fill
                    cell.font = Font(color="FFFFFF", bold=True)
                    
                    # 同时高亮对应的JSON和台账单元格
                    # 差异列前面两列是JSON和台账
                    json_col = col - 2
                    excel_col = col - 1
                    if json_col >= 1:
                        ws.cell(row=row, column=json_col).fill = yellow_fill
                        ws.cell(row=row, column=json_col).font = bold_font
                    if excel_col >= 1:
                        ws.cell(row=row, column=excel_col).fill = yellow_fill
                        ws.cell(row=row, column=excel_col).font = bold_font
                elif cell.value and '✓' in str(cell.value):
                    # 绿色对勾
                    cell.font = Font(color="00AA00", bold=True)
        
        # 调整列宽
        for col in range(1, ws.max_column + 1):
            max_length = 0
            for row in range(1, min(ws.max_row + 1, 100)):
                cell_value = ws.cell(row=row, column=col).value
                if cell_value:
                    max_length = max(max_length, len(str(cell_value)))
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = adjusted_width
        
        # 冻结首行
        ws.freeze_panes = 'A2'
        
        wb.save(file_path)
        print(f"   ✅ 已为差异单元格添加高亮标记")
        
    except Exception as e:
        print(f"   ⚠️  高亮设置失败: {e}")

def compare_orders_by_date_range(json_file_path, excel_file_path, 
                                sheet_name=None, start_date=None, end_date=None):
    """
    对比JSON和Excel数据
    """
    
    # 检查文件
    if not os.path.exists(json_file_path):
        print(f"❌ JSON文件不存在: {json_file_path}")
        return
    if not os.path.exists(excel_file_path):
        print(f"❌ Excel文件不存在: {excel_file_path}")
        return
    
    # 获取日期
    if start_date is None and end_date is None:
        start_date, end_date = get_date_range_from_user()
    
    # 获取子表
    if sheet_name is None:
        sheets = get_excel_sheets(excel_file_path)
        if not sheets:
            return
        sheet_name = select_sheet_interactive(sheets)
    
    print(f"\n📂 使用子表: {sheet_name}")
    if start_date:
        print(f"📅 日期范围: {start_date} 至 {end_date}")
    else:
        print(f"📅 对比所有日期")
    
    # 读取JSON
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        print(f"✅ JSON文件加载成功，共 {len(json_data)} 条记录")
    except Exception as e:
        print(f"❌ 读取JSON文件失败: {e}")
        return
    
    # 转换JSON结构（处理字典格式）
    if isinstance(json_data, dict):
        json_list = []
        for key, value in json_data.items():
            if isinstance(value, dict):
                # 如果value中没有order_no，使用key
                if 'order_no' not in value:
                    value['order_no'] = key
                json_list.append(value)
        json_data = json_list
        print(f"   📋 从字典转换为列表，共 {len(json_data)} 条记录")
    
    # 读取Excel
    try:
        df = pd.read_excel(excel_file_path, sheet_name=sheet_name)
        print(f"✅ Excel文件加载成功，共 {len(df)} 条记录")
    except Exception as e:
        print(f"❌ 读取Excel文件失败: {e}")
        return
    
    # 检查必要列
    required_columns = ['单号', '下单日期']
    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        print(f"❌ Excel缺少必要列: {missing_cols}")
        print(f"   现有列: {list(df.columns)}")
        return
    
    # 筛选日期
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            df['下单日期_dt'] = pd.to_datetime(df['下单日期'], errors='coerce')
            df_filtered = df[(df['下单日期_dt'] >= start) & (df['下单日期_dt'] <= end)]
            print(f"📊 Excel筛选后记录数: {len(df_filtered)}")
        except Exception as e:
            print(f"❌ 日期筛选失败: {e}")
            df_filtered = df
    else:
        df_filtered = df
    
    # 筛选JSON
    json_filtered = []
    if start_date and end_date:
        for item in json_data:
            if not isinstance(item, dict):
                continue
            order_date = item.get('order_date', '')
            if order_date:
                try:
                    if '/' in order_date:
                        parts = order_date.split('/')
                        if len(parts) == 3:
                            dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                            if start <= dt <= end:
                                json_filtered.append(item)
                    elif '-' in order_date:
                        dt = datetime.strptime(order_date, '%Y-%m-%d')
                        if start <= dt <= end:
                            json_filtered.append(item)
                    else:
                        json_filtered.append(item)
                except:
                    json_filtered.append(item)
            else:
                json_filtered.append(item)
        print(f"📊 JSON筛选后记录数: {len(json_filtered)}")
    else:
        json_filtered = json_data
    
    # 创建Excel字典 - 只包含要对比的字段
    excel_dict = {}
    for _, row in df_filtered.iterrows():
        order_no = str(row['单号']) if pd.notna(row['单号']) else ''
        if not order_no or order_no == 'nan':
            continue
        excel_dict[order_no] = {
            'receiver': str(row['收货单位']) if '收货单位' in df.columns and pd.notna(row['收货单位']) else '',
            'address': str(row['收货地址']) if '收货地址' in df.columns and pd.notna(row['收货地址']) else '',
            'contact': str(row['收货人']) if '收货人' in df.columns and pd.notna(row['收货人']) else '',
            'requirement': str(row['客户要求']) if '客户要求' in df.columns and pd.notna(row['客户要求']) else '',
            'quantity': str(row['数量']) if '数量' in df.columns and pd.notna(row['数量']) else '',
            'weight': str(row['重量']) if '重量' in df.columns and pd.notna(row['重量']) else '',
            'shipping': str(row['发运方式']) if '发运方式' in df.columns and pd.notna(row['发运方式']) else '',
            'city': str(row['到货城市']) if '到货城市' in df.columns and pd.notna(row['到货城市']) else '',
            'province': str(row['到货省份']) if '到货省份' in df.columns and pd.notna(row['到货省份']) else '',
            'product': str(row['产品特性']) if '产品特性' in df.columns and pd.notna(row['产品特性']) else ''
        }
    
    # 创建JSON字典 - 只从JSON中提取要对比的字段
    json_dict = {}
    for item in json_filtered:
        if not isinstance(item, dict):
            continue
        order_no = item.get('order_no', '')
        if not order_no:
            continue
        
        # 从JSON中提取字段（匹配JSON的字段名）
        json_dict[order_no] = {
            'receiver': item.get('receiver', ''),      # JSON中对应收货单位
            'address': item.get('address', ''),         # JSON中对应收货地址
            'contact': item.get('contact', ''),         # JSON中对应收货人
            'requirement': item.get('requirement', ''), # JSON中对应客户要求
            'quantity': item.get('quantity', ''),       # JSON中对应数量
            'weight': item.get('weight', ''),           # JSON中对应重量
            'shipping': item.get('发运方式', ''),       # JSON中对应发运方式
            'city': item.get('到货城市', ''),           # JSON中对应到货城市
            'province': item.get('到货省份', ''),       # JSON中对应到货省份
            'product': item.get('危险品类别', '')       # JSON中对应产品特性
        }
    
    # 找出共同订单
    json_orders = set(json_dict.keys())
    excel_orders = set(excel_dict.keys())
    common_orders = json_orders & excel_orders
    json_only = json_orders - excel_orders
    excel_only = excel_orders - json_orders
    
    print(f"\n📊 订单对比:")
    print(f"  JSON订单数: {len(json_orders)}")
    print(f"  台账订单数: {len(excel_orders)}")
    print(f"  共同订单数: {len(common_orders)}")
    if json_only:
        print(f"  ⚠️  JSON多出: {len(json_only)} 个")
    if excel_only:
        print(f"  ⚠️  台账多出: {len(excel_only)} 个")
    
    if len(common_orders) == 0:
        print("❌ 没有共同订单号，无法对比")
        return
    
    # 定义对比字段（JSON字段名 -> 显示名称）
    field_names = {
        'receiver': '收货单位', 
        'address': '收货地址', 
        'contact': '收货人',
        'requirement': '客户要求', 
        'quantity': '数量', 
        'weight': '重量',
        'shipping': '发运方式', 
        'city': '到货城市',
        'province': '到货省份',
        'product': '产品特性'
    }
    
    # 对比数据
    diff_data = []
    field_diff_count = {f: 0 for f in field_names.values()}
    
    print(f"\n🔍 正在对比 {len(common_orders)} 个共同订单...")
    
    for order_no in sorted(common_orders):
        json_item = json_dict[order_no]
        excel_item = excel_dict[order_no]
        
        row = {'订单号': order_no}
        has_diff = False
        
        for field, name in field_names.items():
            j_val = json_item.get(field, '').strip()
            e_val = excel_item.get(field, '').strip()
            row[f'JSON_{name}'] = j_val
            row[f'台账_{name}'] = e_val
            
            # 对比
            if field in ['quantity', 'weight']:
                # 数值字段：提取数字和点
                j_num = re.sub(r'[^\d.]', '', j_val)
                e_num = re.sub(r'[^\d.]', '', e_val)
                if j_num != e_num:
                    row[f'差异_{name}'] = '✗'
                    field_diff_count[name] += 1
                    has_diff = True
                else:
                    row[f'差异_{name}'] = '✓'
            else:
                # 文本字段：清理后比较
                j_clean = clean_text(j_val)
                e_clean = clean_text(e_val)
                if j_clean != e_clean:
                    row[f'差异_{name}'] = '✗'
                    field_diff_count[name] += 1
                    has_diff = True
                else:
                    row[f'差异_{name}'] = '✓'
        
        if has_diff:
            diff_data.append(row)
    
    # 导出差异报告
    if diff_data:
        df_out = pd.DataFrame(diff_data)
        
        # 添加统计信息行
        stats_row = {'订单号': '=== 差异统计 ==='}
        for name in field_names.values():
            stats_row[f'JSON_{name}'] = ''
            stats_row[f'台账_{name}'] = ''
            stats_row[f'差异_{name}'] = field_diff_count[name] if field_diff_count[name] > 0 else ''
        df_out = pd.concat([df_out, pd.DataFrame([stats_row])], ignore_index=True)
        
        # 生成文件名
        date_suffix = ""
        if start_date and end_date:
            if start_date == end_date:
                date_suffix = f"_{start_date}"
            else:
                date_suffix = f"_{start_date}_至_{end_date}"
        
        output_file = f'差异报告{date_suffix}.xlsx'
        
        # 导出Excel
        df_out.to_excel(output_file, index=False)
        print(f"\n✅ 已导出: {output_file}")
        print(f"   共 {len(diff_data)} 个差异订单")
        print(f"   总差异字段: {sum(field_diff_count.values())} 处")
        
        # 应用高亮
        apply_excel_highlighting(output_file)
        
        # 显示各字段差异统计
        print(f"\n📊 各字段差异统计:")
        for name, count in field_diff_count.items():
            if count > 0:
                print(f"   {name}: {count} 处")
                
        print(f"\n💡 提示: Excel中差异单元格已用红色高亮标记，对应的JSON和台账值用黄色高亮")
    else:
        print(f"\n✅ 所有订单完全一致，无差异")

if __name__ == "__main__":
    # 默认文件路径
    json_path = r"D:\project\ppg_wh_agent\output\cache\pending_orders.json"
    excel_path = r"D:\project\WH_check\file\调度台账 2023年6月.xlsx"
    
    print("\n" + "="*60)
    print("🚀 PPG芜湖工业漆 订单对比工具")
    print("="*60)
    
    # 检查文件
    if not os.path.exists(json_path):
        print(f"❌ 找不到JSON文件: {json_path}")
        json_path = input("请输入JSON文件路径: ").strip()
    
    if not os.path.exists(excel_path):
        print(f"❌ 找不到Excel文件: {excel_path}")
        excel_path = input("请输入Excel文件路径: ").strip()
    
    # 执行对比
    compare_orders_by_date_range(
        json_file_path=json_path,
        excel_file_path=excel_path,
        sheet_name=None,
        start_date=None,
        end_date=None
    )