import sys
import os
import json
import logging
import io
import email.utils

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter
from mail.email_saver import save_attachments
from parser.pdf_parser import PDFParser
from parser.content_parser import ContentParser
from business.field_normalizer import FieldNormalizer
from utils.cache_manager import CacheManager

# 屏蔽底层组件的INFO日志，保持最终JSON输出干净
logging.getLogger("parser.content_parser").setLevel(logging.WARNING)
logging.getLogger("parser.pdf_parser").setLevel(logging.WARNING)
logging.getLogger("utils.cache_manager").setLevel(logging.WARNING)
logging.getLogger("mail.email_saver").setLevel(logging.WARNING)
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("business.field_normalizer").setLevel(logging.WARNING)

def test_7_14_pipeline():
    print("=== 开始全流程测试：提取 7.14 的订单并结合 Shipping 缓存 ===")
    
    # 1. 加载现有缓存
    shipping_cache = CacheManager.load_cache()
    
    reader = MailReader()
    # 扩大拉取数量以确保覆盖到 7月14日 的邮件 (随着时间推移，7.14的邮件会越来越靠后)
    import time
    mails = []
    for attempt in range(3):
        try:
            # 搜索 7月13日 至今的所有邮件，因为 7.14 的订单可能是 15/16/17 号才发货！
            mails = reader.fetch_recent(limit=None, search_criteria='(SINCE "13-Jul-2026")') 
            break
        except Exception as e:
            print(f"Fetch attempt {attempt + 1} failed: {e}")
            time.sleep(2)
            
    if not mails:
        print("Failed to fetch emails after multiple attempts.")
        return
    
    target_orders_dict = {}
    
    # 2. 先扫一遍，更新所有的 shipping 缓存 (确保字典是最新的)
    for m in mails:
        mail_type = MailFilter.get_type(m)
        if mail_type == "SHIPPING_INFO":
            msg = m["message"]
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
            
            subject = m.get("subject", "") or msg.get("Subject", "")
            if body:
                new_shipping_data = ContentParser.parse_shipping_mail(subject, body)
                if new_shipping_data:
                    shipping_cache.update(new_shipping_data)
    
    # 实时持久化最新缓存
    CacheManager.save_cache(shipping_cache)
    
    # 3. 筛选 7.14 的 PDF_ORDER 并解析
    for m in mails:
        msg = m["message"]
        date_str = msg.get("Date")
        if not date_str:
            continue
        
        try:
            email_date = email.utils.parsedate_to_datetime(date_str)
            # 判断是否为 7月14日
            if email_date.year == 2026 and email_date.month == 7 and email_date.day == 14:
                mail_type = MailFilter.get_type(m)
                if mail_type == "PDF_ORDER":
                    uid = m["uid"]
                    # 保存附件 (自动跳过非PDF，去重同名)
                    saved_pdfs = save_attachments(uid, msg)
                    
                    for pdf_path in saved_pdfs:
                        # 3.1 提取PDF文字
                        raw_text = PDFParser.parse_pdf(pdf_path)
                        # 3.2 字段初步解析 (传入文件名以便提取交货单号)
                        filename = os.path.basename(pdf_path)
                        parsed_dict = ContentParser.parse_pdf_text(raw_text, filename=filename)
                        # 3.3 业务规则清洗 (例如：从客户要求中提取联系人)
                        normalized_dict = FieldNormalizer.normalize(parsed_dict)
                        
                        # 3.4 拼合 shipping 缓存
                        order_no = normalized_dict.get("order_no", "").strip()
                        
                        # 如果连基本的单号都没提取到（说明这可能不是发货单，而是邮件里夹带的 COA/色板说明 等其他 PDF），直接跳过
                        if not order_no or len(order_no) < 4 or not any(c.isdigit() for c in order_no):
                            continue
                            
                        # 去重逻辑：如果有重复orderno，后面的覆盖前面的
                        target_orders_dict[order_no] = normalized_dict
        except Exception as e:
            import traceback
            print(f"Error processing email {m.get('uid')}: {e}")
            traceback.print_exc()
            
    reader.disconnect()
            
    target_orders = list(target_orders_dict.values())
    print(f"\n成功解析并结合了本地 {len(target_orders)} 个订单（已按订单号去重），正在保存到文件...")
    
    # 将 JSON 结果保存到文件里，方便用户自行查看
    output_path = os.path.join(os.path.dirname(__file__), "..", "output", "test_7_14_orders.json")
    
    # 确保 output 目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(target_orders, f, ensure_ascii=False, indent=4)
        
    print(f"JSON 已成功保存至: {output_path}")

if __name__ == "__main__":
    test_7_14_pipeline()
