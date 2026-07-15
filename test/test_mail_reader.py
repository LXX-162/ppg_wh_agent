import sys
import os
import logging

# 确保能正常引入项目根目录下的包
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mail.mail_reader import MailReader

# 配置基本的日志输出格式，以便查看读取进度
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_mail_reader():
    reader = MailReader()
    
    try:
        # 获取最新的 5 封邮件进行测试
        mails = reader.fetch_recent(limit=5)
        
        print(f"\n读取到邮件数量: {len(mails)}")
        print("==============================")
        
        for m in mails:
            print(f"UID: {m.get('uid')}")
            print(f"Sender: {m.get('sender')}")
            print(f"Subject: {m.get('subject')}")
            print("-" * 30)
            
    except Exception as e:
        print(f"测试过程中出现异常: {e}")
    finally:
        reader.disconnect()

if __name__ == "__main__":
    test_mail_reader()
