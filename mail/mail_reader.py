import imaplib
import email
from email import policy
import logging
from utils.config import load_config

logger = logging.getLogger(__name__)

class MailReader:
    def __init__(self):
        config = load_config()
        self.host = config.get("IMAP_HOST")
        self.user = config.get("IMAP_USER")
        self.password = config.get("IMAP_PASS")
        self.port = 993
        self.mail = None

    def connect(self):
        logger.info("连接邮箱...")
        self.mail = imaplib.IMAP4_SSL(self.host, self.port)
        self.mail.login(self.user, self.password)
        logger.info("登录成功")

    def disconnect(self):
        if self.mail:
            try:
                self.mail.logout()
            except Exception:
                pass
            self.mail = None

    def fetch_recent(self, limit=20, search_criteria="ALL"):
        if not self.mail:
            self.connect()

        self.mail.select("INBOX")
        status, response = self.mail.uid("SEARCH", None, search_criteria)
        if status != "OK":
            logger.error(f"检索邮件失败: {search_criteria}")
            return []

        uids = response[0].split()
        logger.info(f"搜索条件 '{search_criteria}' 匹配到邮件数量: {len(uids)}")

        recent_uids = uids[-limit:] if limit else uids
        mails = []

        for uid in recent_uids:
            status, fetch_data = self.mail.uid("FETCH", uid, "(RFC822)")
            if status != "OK":
                continue

            for response_part in fetch_data:
                if isinstance(response_part, tuple):
                    msg_bytes = response_part[1]
                    # 使用 default policy 自动处理 header 解码等
                    msg = email.message_from_bytes(msg_bytes, policy=policy.default)
                    
                    mails.append({
                        "uid": uid.decode('utf-8'),
                        "sender": str(msg.get("From", "")),
                        "subject": str(msg.get("Subject", "")),
                        "date": str(msg.get("Date", "")),
                        "message": msg
                    })
        
        return mails
