import sys
import os
import logging

# 确保能正常引入项目根目录下的包
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mail.mail_reader import MailReader
from mail.email_saver import save_attachments

# 减少其他模块日志的干扰，只关注当前脚本执行和保存逻辑
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_save_pdf():
    reader = MailReader()
    
    try:
        mails = reader.fetch_recent(limit=5)
        print(f"\n成功读取到 {len(mails)} 封邮件，准备开始提取 PDF 附件...")
        print("======================================================")
        
        total_saved = 0
        
        for m in mails:
            uid = m["uid"]
            msg = m["message"]
            
            # 调用保存附件方法
            saved_paths = save_attachments(uid, msg)
            
            if saved_paths:
                print(f"UID: {uid} | 保存了 {len(saved_paths)} 个 PDF:")
                for path in saved_paths:
                    print(f"  -> {path}")
                print("-" * 54)
                total_saved += len(saved_paths)
            
        print(f"\n执行完毕！总共保存了 {total_saved} 个 PDF 附件。")
            
    except Exception as e:
        print(f"执行出错: {e}")
    finally:
        reader.disconnect()

if __name__ == "__main__":
    test_save_pdf()
