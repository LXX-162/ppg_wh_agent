import sys
import os
import logging
import io
import time
import email.utils
from datetime import datetime

# 强制控制台输出使用 utf-8 编码，防止 Windows GBK 报错
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from utils.config import load_config
from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter
from mail.email_saver import save_attachments
from parser.pdf_parser import PDFParser
from parser.content_parser import ContentParser
from business.field_normalizer import FieldNormalizer
from utils.cache_manager import CacheManager, PendingOrdersManager
from utils.seen_mails import SeenMailsManager

# 屏蔽底层组件的 INFO 日志
logging.getLogger("parser.content_parser").setLevel(logging.WARNING)
logging.getLogger("parser.pdf_parser").setLevel(logging.WARNING)
logging.getLogger("utils.cache_manager").setLevel(logging.WARNING)
logging.getLogger("mail.email_saver").setLevel(logging.WARNING)
logging.getLogger("mail.mail_reader").setLevel(logging.WARNING)
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("business.field_normalizer").setLevel(logging.WARNING)
logging.getLogger("business.normalizers").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def _extract_body(msg) -> str:
    """从邮件对象提取纯文本正文。"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def main():
    logger.info("=== PPG WH Agent — 邮件处理 ===")

    # ── 1. 加载已读邮件记录 & shipping 全量缓存 ──────────────────────
    seen_uids = SeenMailsManager.load()
    shipping_cache = CacheManager.load_cache()

    reader = MailReader()

    try:
        # ── 2. 拉取邮件（带重试机制） ────────────────────────────────
        mails = []
        for attempt in range(3):
            try:
                mails = reader.fetch_recent(limit=None, search_criteria='ALL')
                if mails:
                    break
            except Exception as e:
                logger.warning(f"拉取邮件第 {attempt + 1} 次失败: {e}")
                time.sleep(2)

        if not mails:
            logger.error("多次尝试后仍无法拉取邮件，退出")
            return

        logger.info(f"共获取 {len(mails)} 封邮件")

        # ── 3. 第一遍：更新 shipping 缓存（不受已读限制） ────────────
        shipping_updated = False
        for m in mails:
            if MailFilter.get_type(m) != "SHIPPING_INFO":
                continue
            msg = m["message"]
            body = _extract_body(msg)
            subject = m.get("subject", "") or str(msg.get("Subject", ""))
            if body:
                new_data = ContentParser.parse_shipping_mail(subject, body)
                if new_data:
                    shipping_cache.update(new_data)
                    shipping_updated = True

        if shipping_updated:
            today = datetime.today().strftime("%Y-%m-%d")
            CacheManager.save_cache(shipping_cache, date_str=today)

        # ── 4. 第二遍：解析 PDF_ORDER，跳过已处理邮件 ────────────────
        new_orders_dict = {}
        processed_uids = []

        for m in mails:
            uid = m["uid"]
            if SeenMailsManager.is_seen(uid, seen_uids):
                continue
            if MailFilter.get_type(m) != "PDF_ORDER":
                continue

            msg = m["message"]
            saved_pdfs = save_attachments(uid, msg)

            for pdf_path in saved_pdfs:
                raw_text = PDFParser.parse_pdf(pdf_path)
                filename = os.path.basename(pdf_path)
                parsed = ContentParser.parse_pdf_text(raw_text, filename=filename)
                normalized = FieldNormalizer.normalize(parsed)

                order_no = normalized.get("order_no", "").strip()
                if not order_no or len(order_no) < 4 or not any(c.isdigit() for c in order_no):
                    continue

                if order_no in shipping_cache:
                    sc = shipping_cache[order_no]
                    normalized.setdefault("发运方式", sc.get("shipping", ""))
                    normalized.setdefault("危险品类别", sc.get("danger", ""))

                new_orders_dict[order_no] = normalized

            seen_uids.add(str(uid))
            processed_uids.append(uid)

        # ── 5. 合并写入暂存区 ────────────────────────────────────────
        new_orders = list(new_orders_dict.values())
        if new_orders:
            PendingOrdersManager.add_orders(new_orders)
        else:
            logger.info("本次运行未发现新订单")

        # ── 6. 持久化已读记录 ────────────────────────────────────────
        SeenMailsManager.save(seen_uids)

        # ── 7. 输出摘要 ─────────────────────────────────────────────
        if processed_uids:
            total = len(processed_uids)
            # 按每10条一组输出 UID 列表
            for i in range(0, total, 10):
                batch = processed_uids[i:i + 10]
                end = min(i + 10, total)
                logger.info(f"处理 {i+1}~{end} 单: UID {', '.join(batch)}")
            logger.info(f"新增订单: {len(new_orders)} 条，写入 {PendingOrdersManager.CACHE_FILE}")
        else:
            logger.info("本次运行未发现新订单")
        pending_count = len(PendingOrdersManager.get_by_status("pending"))
        logger.info(f"当前待写入: {pending_count} 条")

    except Exception as e:
        logger.error(f"执行异常: {e}", exc_info=True)
    finally:
        reader.disconnect()


if __name__ == "__main__":
    main()
