import sys
import os
import json
import logging
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter

def dump_shipping_emails():
    reader = MailReader()
    mails = reader.fetch_recent(limit=None, search_criteria='(SINCE "13-Jul-2026")')
    
    with open("shipping_emails_dump.txt", "w", encoding="utf-8") as f:
        for m in mails:
            if MailFilter.get_type(m) == "SHIPPING_INFO":
                f.write(f"--- 找到 SHIPPING_INFO 邮件: UID {m['uid']} --- \n")
                
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
                        
                f.write(body + "\n")
                f.write("="*50 + "\n")
                
    reader.disconnect()
    print("已将所有 SHIPPING_INFO 邮件内容导出到 shipping_emails_dump.txt，请提供部分内容让我看看格式！")

if __name__ == "__main__":
    dump_shipping_emails()
