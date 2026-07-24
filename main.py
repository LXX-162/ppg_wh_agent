import sys
import os
import logging
import io
import time
import re
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
    """从邮件对象提取纯文本正文，并截断历史回复内容。"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    cutoff = body.find("-----Original Message-----")
                    if cutoff != -1:
                        body = body[:cutoff]
                    return body.strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            cutoff = body.find("-----Original Message-----")
            if cutoff != -1:
                body = body[:cutoff]
            return body.strip()
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
                # 断开旧连接，下次 fetch_recent 内部会重新连接
                reader.disconnect()
                time.sleep(3)

        if not mails:
            logger.error("多次尝试后仍无法拉取邮件，退出")
            return

        logger.info(f"共获取 {len(mails)} 封邮件")

        # ── 3. 第一遍：更新 shipping 缓存（不受已读限制） ────────────
        # 规则：
        #   - wenjuan 邮件（不限类型）：从标题提取发运方式，覆盖已有记录。
        #     订单号来源：1) 正文表格 2) PDF 附件名中的 11 开头数字 3) 正文中 11 开头的数字
        #   - 其他人 SHIPPING_INFO 邮件：仅在缓存中不存在时写入（首次写入后永不覆盖）
        shipping_updated = False
        for m in mails:
            sender = m.get("sender", "").lower()
            is_wenjuan = ("wenjuan" in sender or
                          ("juan" in sender and "wen" in sender))

            is_shipping_info = MailFilter.get_type(m) == "SHIPPING_INFO"
            is_other_shipping = is_shipping_info and not is_wenjuan

            # 只处理：wenjuan 的所有邮件 + 其他人的 SHIPPING_INFO 邮件
            if not (is_wenjuan or is_shipping_info):
                continue

            msg = m["message"]
            subject = m.get("subject", "") or str(msg.get("Subject", ""))

            if is_wenjuan:
                # wenjuan 邮件：从标题取发运方式
                shipping_from_subject = ""
                for kw in ["保温车", "包车", "零担", "自提"]:
                    if kw in subject:
                        shipping_from_subject = kw
                        break
                if not shipping_from_subject:
                    continue

                # 收集订单号：仅从正文开头 200 字符 + PDF 附件名
                # 注意：不扫描整个正文，避免回复链中的历史订单号污染
                order_nos = set()
                body = _extract_body(msg)

                if body:
                    body_head = body[:200].strip()
                    # 1) 从正文表格解析（仅用正文开头）
                    table_data = ContentParser.parse_shipping_mail(subject, body_head)
                    if table_data:
                        order_nos.update(table_data.keys())
                    # 2) 正文开头中的 11 开头数字
                    body_orders = re.findall(r'(11\d{6,8})', body_head)
                    order_nos.update(body_orders)

                # 3) 从 PDF 附件名提取（不限范围）
                if msg.is_multipart():
                    for part in msg.walk():
                        filename = part.get_filename()
                        if filename:
                            fn_orders = re.findall(r'(11\d{6,8})', filename)
                            order_nos.update(fn_orders)

                if order_nos:
                    for on in order_nos:
                        cur = shipping_cache.get(on, {})
                        if cur.get("shipping") != shipping_from_subject:
                            shipping_cache[on] = {"shipping": shipping_from_subject,
                                                  "danger": cur.get("danger", "")}
                            shipping_updated = True
            else:
                # 其他人 SHIPPING_INFO 邮件：首次写入后永不覆盖
                body = _extract_body(msg)
                if not body:
                    continue
                new_data = ContentParser.parse_shipping_mail(subject, body)
                if not new_data:
                    continue
                for order_no, info in new_data.items():
                    if order_no not in shipping_cache:
                        shipping_cache[order_no] = info
                        shipping_updated = True

        if shipping_updated:
            today = datetime.today().strftime("%Y-%m-%d")
            CacheManager.save_cache(shipping_cache, date_str=today)

        # ── 4. 处理邮件正文的业务指令（更新/取消/拆单）────────────
        #    所有指令检测仅基于邮件正文开头 200 字符（新邮件开头才是真实意图）
        cancel_orders      = set()      # 要取消的订单号
        update_instructions = {}        # { order_no: {新订单字段...} }
        split_new_orders   = {}         # { 新订单号: {订单字段...} }

        BODY_HEAD_LEN = 200  # 只检测正文开头范围

        for m in mails:
            uid = m["uid"]
            msg = m["message"]
            body = _extract_body(msg)
            subject = m.get("subject", "") or str(msg.get("Subject", ""))

            if not body and not subject:
                continue

            # 正文开头（不含回复链）
            body_head = body[:BODY_HEAD_LEN].strip()
            body_head_lower = body_head.lower()
            # 正文开头+主题（这里主题也纳入检测，因为有些更新订单号在主题中）
            head_text = f"{subject} {body_head}"

            # ── 4a. 取消指令 ──────────────────────────────────────
            # 格式如："11915908 /11915959---停止备料和提货"
            # 取消关键词在正文开头附近：停止 / 作废 / 不用发 / 取消
            is_cancel = (
                "停止" in body_head_lower or
                "作废" in body_head_lower or
                "不用发" in body_head_lower or
                "取消" in body_head_lower
            )

            if is_cancel:
                logger.info(f"[指令-取消] UID={uid}: {subject[:60]}")
                # 仅从正文开头 200 字符提取订单号
                cancel_orders_in_head = re.findall(r'(11\d{6,8})', body_head)
                # 也检查主题
                cancel_orders_in_subject = re.findall(r'(11\d{6,8})', subject)
                all_found = set(cancel_orders_in_head) | set(cancel_orders_in_subject)
                for on in all_found:
                    cancel_orders.add(on)
                    logger.info(f"  → 取消订单 {on}")

            # ── 4b. 更新指令 ──────────────────────────────────────
            # 格式如："11757549发货单更新" 或 "附件更新发货单，请以此份为准"
            # 更新关键词在正文开头附近：更新 / 以此为准 / 重新提供
            is_update = (
                "更新" in body_head_lower or
                "以此为准" in body_head_lower or
                "重新提供" in body_head_lower
            )

            if is_update:
                logger.info(f"[指令-更新] UID={uid}: {subject[:60]}")
                # 从正文开头+主题提取待更新订单号
                update_targets = re.findall(r'(11\d{6,8})', head_text)
                if update_targets:
                    saved_pdfs = save_attachments(uid, msg)
                    for pdf_path in saved_pdfs:
                        raw_text = PDFParser.parse_pdf(pdf_path)
                        filename = os.path.basename(pdf_path)
                        parsed = ContentParser.parse_pdf_text(raw_text, filename=filename)
                        normalized = FieldNormalizer.normalize(parsed)
                        pdf_order_no = normalized.get("order_no", "").strip()
                        if not pdf_order_no or len(pdf_order_no) < 4:
                            continue
                        if pdf_order_no in shipping_cache:
                            sc = shipping_cache[pdf_order_no]
                            normalized.setdefault("发运方式", sc.get("shipping", ""))
                            if not normalized.get("危险品类别"):
                                normalized["危险品类别"] = sc.get("danger", "")
                        # PDF 原文解析结果覆盖（优先级最高）
                        pdf_danger = parsed.get("pdf_danger", "")
                        if pdf_danger:
                            if not normalized.get("危险品类别"):
                                normalized["危险品类别"] = pdf_danger
                        update_instructions[pdf_order_no] = normalized
                        logger.info(f"  → 更新订单 {pdf_order_no}（来自 PDF）")

            # ── 4c. 拆单指令 ──────────────────────────────────────
            # 格式如："附件单据已拆，请查收"
            # 仅在正文开头附近出现"拆"且附件有 >= 2 个 PDF
            if "拆" in body_head or "拆" in subject:
                saved_pdfs = save_attachments(uid, msg)
                pdf_attachments = [p for p in saved_pdfs if p.lower().endswith('.pdf')]
                if len(pdf_attachments) >= 2:
                    logger.info(f"[指令-拆单] UID={uid}: {subject[:60]}")
                    parsed_list = []
                    for pdf_path in pdf_attachments:
                        raw_text = PDFParser.parse_pdf(pdf_path)
                        filename = os.path.basename(pdf_path)
                        parsed = ContentParser.parse_pdf_text(raw_text, filename=filename)
                        normalized = FieldNormalizer.normalize(parsed)
                        pdf_order_no = normalized.get("order_no", "").strip()
                        if not pdf_order_no:
                            continue
                        if pdf_order_no in shipping_cache:
                            sc = shipping_cache[pdf_order_no]
                            normalized.setdefault("发运方式", sc.get("shipping", ""))
                            if not normalized.get("危险品类别"):
                                normalized["危险品类别"] = sc.get("danger", "")
                        pdf_danger = parsed.get("pdf_danger", "")
                        if pdf_danger:
                            if not normalized.get("危险品类别"):
                                normalized["危险品类别"] = pdf_danger
                        parsed_list.append((pdf_order_no, normalized, filename))

                    if len(parsed_list) >= 2:
                        original_on, original_data, _ = parsed_list[0]
                        update_instructions[original_on] = original_data
                        logger.info(f"  → 原单 {original_on} 已标记更新（拆单）")

                        new_on, new_data, new_fn = parsed_list[1]
                        if new_on == original_on:
                            new_on_with_suffix = f"{original_on}-1"
                        else:
                            new_on_with_suffix = new_on
                        new_data["order_no"] = new_on_with_suffix
                        split_new_orders[new_on_with_suffix] = new_data
                        logger.info(f"  → 拆分子单 {new_on_with_suffix}（来自 {new_fn}）")

        # ── 执行取消指令 ──────────────────────────────────────────
        if cancel_orders:
            pending = PendingOrdersManager.load_pending()
            any_change = False
            for on in cancel_orders:
                if on in pending:
                    pending[on]["sync_status"] = "已取消"
                    pending[on]["synced_at"] = None
                    any_change = True
                    logger.info(f"  → [取消] 订单 {on} 已标记为 已取消（保留原订单信息）")
                else:
                    logger.info(f"  → [取消] 订单 {on} 不在暂存区，跳过（不新建空记录）")
            if any_change:
                PendingOrdersManager.save_pending(pending)
            logger.info(f"[取消] 共处理 {len(cancel_orders)} 条（实际修改 {sum(1 for on in cancel_orders if on in pending)} 条）")

        # ── 执行更新指令 ──────────────────────────────────────────
        if update_instructions:
            update_list = []
            for on, data in update_instructions.items():
                data["sync_status"] = "已更新"
                data["synced_at"] = None
                update_list.append(data)
            PendingOrdersManager.add_orders(update_list)
            logger.info(f"[更新] 共更新 {len(update_instructions)} 条订单")

        # ── 执行拆单新增指令 ──────────────────────────────────────
        if split_new_orders:
            # 将原单和新单的 sync_status 都设为"拆单"
            # 原单在 update_instructions 中
            for on in split_new_orders:
                if on in update_instructions:
                    update_instructions[on]["sync_status"] = "拆单"
                    update_instructions[on]["synced_at"] = None
            # 新单
            split_list = []
            for on, data in split_new_orders.items():
                data["sync_status"] = "拆单"
                data["synced_at"] = None
                split_list.append(data)
            PendingOrdersManager.add_orders(split_list)
            logger.info(f"[拆单] 共新增 {len(split_new_orders)} 条子订单（状态=拆单）")

        # ── 5. 第二遍：解析 PDF_ORDER，跳过已处理邮件 ────────────────
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
                    if not normalized.get("危险品类别"):
                        normalized["危险品类别"] = sc.get("danger", "")
                # 如果 shipping 缓存中没有危险品类别，从 PDF 中提取
                if not normalized.get("危险品类别"):
                    pdf_danger = parsed.get("pdf_danger", "")
                    if pdf_danger:
                        normalized["危险品类别"] = pdf_danger

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
