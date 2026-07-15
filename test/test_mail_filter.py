import sys
import os
import logging

# 确保能正常引入项目根目录下的包
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter

# 减少日志输出，突出打印结果
logging.basicConfig(level=logging.WARNING)

def test_mail_filter():
    reader = MailReader()
    
    try:
        # 获取最近20封邮件来确保有足够的多样性进行测试
        mails = reader.fetch_recent(limit=20)
        
        print("\n=== 邮件分类测试 ===")
        
        for m in mails:
            sender = m.get("sender", "Unknown Sender")
            mail_type = MailFilter.get_type(m)
            
            print(sender)
            print("↓")
            print(mail_type)
            print("-" * 30)
            
    except Exception as e:
        print(f"执行出错: {e}")
    finally:
        reader.disconnect()

if __name__ == "__main__":
    test_mail_filter()
