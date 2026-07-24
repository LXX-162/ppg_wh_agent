"""
修复 pending_orders 中特定订单的危险品类别为空白的问题。
直接从 PDF 重新提取危险品类别并更新。
"""
import sys, json, copy, glob, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from parser.pdf_parser import PDFParser
from parser.content_parser import ContentParser
from business.field_normalizer import FieldNormalizer
from utils.cache_manager import CacheManager, PendingOrdersManager

shipping_cache = CacheManager.load_cache()

# 需要修复的订单
TARGET_ORDERS = ['11967912', '11967921', '11967927', '11967930']

new_orders_dict = {}
for oid in TARGET_ORDERS:
    for f in sorted(glob.glob(f'file/pdf/*{oid}*')):
        raw = PDFParser.parse_pdf(f)
        norm = ContentParser.normalize_text(raw)
        parsed = ContentParser.parse_pdf_text(norm, f)
        normalized = FieldNormalizer.normalize(copy.deepcopy(parsed))
        
        order_no = normalized.get('order_no', '').strip()
        if not order_no:
            continue
        
        # main.py 第二遍补充逻辑
        if order_no in shipping_cache:
            sc = shipping_cache[order_no]
            normalized.setdefault('发运方式', sc.get('shipping', ''))
            if not normalized.get('危险品类别'):
                normalized['危险品类别'] = sc.get('danger', '')
        if not normalized.get('危险品类别'):
            pdf_danger = parsed.get('pdf_danger', '')
            if pdf_danger:
                normalized['危险品类别'] = pdf_danger
        
        new_orders_dict[order_no] = normalized

if new_orders_dict:
    PendingOrdersManager.add_orders(list(new_orders_dict.values()))
    print(f'已更新 {len(new_orders_dict)} 条订单:')
    pending = PendingOrdersManager.load_pending()
    for oid in TARGET_ORDERS:
        for k, v in pending.items():
            if v.get('order_no') == oid:
                print(f'  {oid}: 危险品类别={repr(v.get("危险品类别"))} pdf_danger={repr(v.get("pdf_danger"))}')
                break
else:
    print('未找到匹配的订单')
