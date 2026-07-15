import sys
import os
import json
import logging
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter
from parser.content_parser import ContentParser

def test_parse_shipping():
    reader = MailReader()
    mails = reader.fetch_recent(limit=30)
    
    print("=== 测试: 解析 Shipping 邮件正文表格 ===")
    
    for m in mails:
        if MailFilter.get_type(m) == "SHIPPING_INFO":
            print(f"\n找到 SHIPPING_INFO 邮件: UID {m['uid']}")
            
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
            
            if body:
                result = ContentParser.parse_shipping_mail(m.get("subject", ""), body)
                print("解析结果:")
                print(json.dumps(result, ensure_ascii=False, indent=4))
            
            # 测试一封就行
            break
            
    reader.disconnect()

if __name__ == "__main__":
    test_parse_shipping()
