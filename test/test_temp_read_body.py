import sys
import os
import json
import logging
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter

def print_shipping_body():
    reader = MailReader()
    mails = reader.fetch_recent(limit=20)
    
    for m in mails:
        if MailFilter.get_type(m) == "SHIPPING_INFO":
            print(f"--- 找到 SHIPPING_INFO 邮件: UID {m['uid']} ---")
            
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
                    
            print(body)
            print("="*50)
            break
            
    reader.disconnect()

if __name__ == "__main__":
    print_shipping_body()
