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
        logger.info(f"  IMAP SSL 连接中: {self.host}:{self.port}...")
        self.mail = imaplib.IMAP4_SSL(self.host, self.port)
        logger.info(f"  SSL 握手完成，登录用户: {self.user}")
        self.mail.login(self.user, self.password)
        logger.info("  登录成功")

    def disconnect(self):
        if self.mail:
            try:
                self.mail.logout()
            except Exception:
                pass
            self.mail = None

    def fetch_recent(self, limit=20, search_criteria="ALL", skip_uids: set = None):
        if not self.mail:
            self.connect()

        try:
            self.mail.select("INBOX")
        except Exception:
            # 连接已断开，重新连接
            self.disconnect()
            self.connect()
            self.mail.select("INBOX")

        status, response = self.mail.uid("SEARCH", None, search_criteria)
        if status != "OK":
            logger.error(f"检索邮件失败: {search_criteria}")
            return []

        uids = response[0].split()
        logger.info(f"搜索条件 '{search_criteria}' 匹配到邮件数量: {len(uids)}")

        # ── 客户端过滤已读 UID，只下载未读邮件 ──────────────────────────
        # SEARCH 返回的只是 UID 文本列表（很快）；真正耗时的是 FETCH（下载邮件正文）。
        # 在这里提前过滤，可以避免重复下载已处理过的历史邮件，无需限制搜索日期范围。
        if skip_uids:
            before = len(uids)
            uids = [uid for uid in uids if uid.decode('utf-8') not in skip_uids]
            skipped = before - len(uids)
            logger.info(f"过滤已读后，待下载未读邮件: {len(uids)} 封（跳过已读 {skipped} 封）")

        recent_uids = uids[-limit:] if limit else uids
        mails = []

        total = len(recent_uids)
        for i, uid in enumerate(recent_uids):
            if total > 10 and i % 10 == 0:
                logger.info(f"  下载邮件进度: {i}/{total}...")
            try:
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
            except imaplib.IMAP4.error as e:
                logger.warning(f"FETCH UID={uid.decode('utf-8', errors='replace')} 失败（跳过）: {e}")
            except Exception as e:
                logger.warning(f"解析 UID={uid.decode('utf-8', errors='replace')} 邮件时出错（跳过）: {e}")
        logger.info(f"  下载完成，共 {len(mails)} 封")

        return mails
