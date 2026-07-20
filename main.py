import sys
import os
import logging
import io
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting PPG WH Agent — Mail Processing...")

    # ── 1. 加载已读邮件记录 & shipping 全量缓存 ──────────────────────
    seen_uids = SeenMailsManager.load()
    logger.info(f"已读邮件记录：{len(seen_uids)} 封")

    shipping_cache = CacheManager.load_cache()  # 加载全量合并缓存
    logger.info(f"已加载发货缓存，当前缓存订单数量: {len(shipping_cache)}")

    reader = MailReader()

    try:
        mails = reader.fetch_recent(limit=50)
        logger.info(f"成功获取 {len(mails)} 封最近的邮件，开始处理...")

        # ── 2. 第一遍：更新 shipping 缓存（不受已读限制） ────────────
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
                    logger.info(f"[UID {m['uid']}] 解析出 {len(new_data)} 条发货信息")
                    shipping_cache.update(new_data)
                    shipping_updated = True

        if shipping_updated:
            today = datetime.today().strftime("%Y-%m-%d")
            CacheManager.save_cache(shipping_cache, date_str=today)

        # ── 3. 第二遍：解析 PDF_ORDER，跳过已处理邮件 ────────────────
        new_orders: list = []

        for m in mails:
            uid = m["uid"]

            if SeenMailsManager.is_seen(uid, seen_uids):
                logger.debug(f"[UID {uid}] 已处理，跳过")
                continue

            if MailFilter.get_type(m) != "PDF_ORDER":
                continue

            logger.info(f"-> [UID {uid}] 检测到 PDF_ORDER，开始解析...")
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

                # 从 shipping 缓存补全发运方式和危险品类别
                if order_no in shipping_cache:
                    sc = shipping_cache[order_no]
                    normalized.setdefault("发运方式", sc.get("shipping", ""))
                    normalized.setdefault("危险品类别", sc.get("danger", ""))

                new_orders.append(normalized)

            # 标记该邮件为已处理
            seen_uids.add(str(uid))

        # ── 4. 合并写入暂存区 pending_orders.json ────────────────────
        if new_orders:
            PendingOrdersManager.add_orders(new_orders)
            logger.info(f"共解析并暂存 {len(new_orders)} 条新订单")
        else:
            logger.info("本次运行未发现新订单")

        # ── 5. 持久化已读记录 ────────────────────────────────────────
        SeenMailsManager.save(seen_uids)

        logger.info("=== 邮件处理完成 ===")
        pending_count = len(PendingOrdersManager.get_by_status("pending"))
        logger.info(f"当前 pending 订单数量: {pending_count}")

    except Exception as e:
        logger.error(f"执行异常: {e}", exc_info=True)
    finally:
        reader.disconnect()


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


if __name__ == "__main__":
    main()
