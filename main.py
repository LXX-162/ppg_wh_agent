import sys
import os
import subprocess

# ── 第一步：确保依赖已安装（在所有其他导入之前） ──────────────────
def ensure_dependencies():
    """检查并自动安装 jionlp"""
    try:
        import jionlp
        print("✅ jionlp 已安装")
        return True
    except ImportError:
        print("⚠️ jionlp 未安装，正在自动安装...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "jionlp",
                "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple",
                "--timeout", "120",
                "--no-cache-dir"
            ])
            print("✅ jionlp 安装成功")
            return True
        except Exception as e:
            print(f"❌ jionlp 安装失败: {e}")
            # 尝试备用源
            try:
                print("🔄 尝试备用源安装...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "jionlp",
                    "--index-url", "https://mirrors.aliyun.com/pypi/simple/",
                    "--timeout", "120"
                ])
                print("✅ jionlp 安装成功")
                return True
            except Exception as e2:
                print(f"❌ 备用源安装也失败: {e2}")
                return False

# 在导入任何其他模块之前先安装依赖
if not ensure_dependencies():
    print("❌ 关键依赖安装失败，程序退出")
    sys.exit(1)

# ── 第二步：现在才导入其他模块 ──────────────────────────────────────
import io
import logging
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



# ── 邮件回复链 / 转发链边界识别 ────────────────────────────────────────────
# 飞书 / Outlook 转发的典型格式（在"新内容"之后另起一行出现）：
#   From: He, Jinlan
#   Sent: Saturday, August 1, 2026 12:38 PM
#   To: 'cs05@efs.com.cn'; ...
#
# 或中文格式：
#   发件人: 何金兰
#   发送时间: 2026年8月1日 12:38
#   收件人: ...
#
# 或经典格式：
#   -----Original Message-----
_EMAIL_FORWARD_PATTERNS = [
    # 经典 Western 邮件
    re.compile(r'-----Original Message-----'),
    # Outlook / Feishu 英文转发头：From: xxx 后跟 Sent: / 发送时间:
    re.compile(r'^\s*From:\s*.+?\n(?:[^\n]*\n){0,4}?\s*(?:Sent|发送时间):\s*', re.MULTILINE),
    # 中文转发头：
    re.compile(r'^\s*(?:发件人|寄件人):\s*.+?\n(?:[^\n]*\n){0,3}?\s*(?:发送时间|送出时间):\s*', re.MULTILINE),
]


def _cut_at_reply_chain(body: str) -> str:
    """
    在正文中定位"回复 / 转发链"的起始位置并截断。
    返回只含新邮件内容（不含历史回复）的正文；找不到边界时原样返回。
    """
    best = len(body)
    for pat in _EMAIL_FORWARD_PATTERNS:
        m = pat.search(body)
        if m and m.start() < best:
            best = m.start()
    return body[:best]


def _extract_body(msg) -> str:
    """从邮件对象提取纯文本正文，并在"回复/转发链"起始处截断。"""
    body_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    part_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    if part_text.strip():
                        body_parts.append(part_text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            part_text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if part_text.strip():
                body_parts.append(part_text)

    if not body_parts:
        return ""

    # 取第一个非空 plain/text 部分，并截断回复/转发链
    body = _cut_at_reply_chain(body_parts[0])
    return body.strip()


def _parse_pdf_docket(pdf_path: str) -> dict:
    """
    解析发货单 PDF：
      - 先从 PDF【字符坐标层】精确提取"发货单号"（PDF 内部印刷的权威单号，不依赖文件名的
        对不对），再结合文本与文件名解析各字段。
    """
    raw_text = PDFParser.parse_pdf(pdf_path)
    coord_order_no = PDFParser.extract_order_no_coord(pdf_path)
    filename = os.path.basename(pdf_path)
    return ContentParser.parse_pdf_text(raw_text, filename=filename, coord_order_no=coord_order_no)


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
                # wenjuan 邮件：从标题取发运方式。
                # 规则：仅在【正文无内容 且 附件为 PDF】时，wenjuan 主题才作为发运方式来源。
                # 排除"以下发货缺少附件"一类的缺件表格邮件（正文有内容、列出
                # 发货单号/SO/收货人/Item Number/批次/COA/色板），这类邮件主题虽常带
                # "零担/保温车"等字样，但并非真实发运方式，会污染发运方式缓存。
                body = _extract_body(msg)

                # 判断是否携带 PDF 发货单附件
                has_pdf_attach = False
                if msg.is_multipart():
                    for part in msg.walk():
                        filename = part.get_filename()
                        if filename and filename.lower().endswith(".pdf"):
                            has_pdf_attach = True
                            break

                # 正文有内容（如缺件表格/说明）或没有 PDF 附件 → 不采用 wenjuan 主题
                if body or not has_pdf_attach:
                    continue

                shipping_from_subject = ""
                for kw in ["保温车", "包车", "零担", "自提"]:
                    if kw in subject:
                        shipping_from_subject = kw
                        break
                if not shipping_from_subject:
                    continue

                # 该场景正文为空，订单号来源为：PDF 附件名 + 主题
                order_nos = set()
                if msg.is_multipart():
                    for part in msg.walk():
                        filename = part.get_filename()
                        if filename:
                            fn_orders = re.findall(r'(11\d{6,8})', filename)
                            order_nos.update(fn_orders)
                subject_orders = re.findall(r'(11\d{6,8})', subject)
                order_nos.update(subject_orders)

                if order_nos:
                    for on in order_nos:
                        cur = shipping_cache.get(on, {})
                        if cur.get("shipping") != shipping_from_subject:
                            # 保留原有 danger（正文为空无法从表格提取）
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
        #    正文已由 _extract_body 在"回复/转发链"处截断，
        #    因此全文即"新邮件内容"，业务指令只基于新内容检测。
        cancel_orders      = set()      # 要取消的订单号
        update_instructions = {}        # { order_no: {新订单字段...} }
        split_new_orders   = {}         # { 新订单号: {订单字段...} }

        for m in mails:
            uid = m["uid"]
            msg = m["message"]
            body = _extract_body(msg)
            subject = m.get("subject", "") or str(msg.get("Subject", ""))

            if not body and not subject:
                continue

            # 正文（不含回复链）
            body_head = body.strip()
            body_head_lower = body_head.lower()
            # 正文+主题（这里主题也纳入检测，因为有些更新订单号在主题中）
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
                # 从正文（不含回复链）+ 主题提取订单号
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
                        parsed = _parse_pdf_docket(pdf_path)
                        normalized = FieldNormalizer.normalize(parsed)
                        pdf_order_no = normalized.get("order_no", "").strip()
                        # 严格校验：必须是合法的 8 位发货单号，过滤 SO 单号等非法值
                        if not pdf_order_no or not ContentParser._is_order_no(pdf_order_no.split('-')[0]):
                            logger.info(f"  → 跳过非法订单号 {pdf_order_no!r}（更新指令）")
                            continue

                        # 过滤无效解析结果：必须至少有地址、重量或数量等核心字段
                        has_core_field = bool(
                            normalized.get("address") or
                            normalized.get("weight") or
                            normalized.get("quantity") or
                            normalized.get("company_name")
                        )
                        if not has_core_field:
                            logger.info(f"  → 跳过空解析结果 {pdf_order_no}（来自 {filename}）")
                            continue

                        if pdf_order_no in shipping_cache:
                            sc = shipping_cache[pdf_order_no]
                            normalized.setdefault("发运方式", sc.get("shipping", ""))
                        # 优先级：PDF 解析结果 > shipping 缓存
                        if not normalized.get("危险品类别"):
                            pdf_danger = parsed.get("pdf_danger", "")
                            if pdf_danger:
                                normalized["危险品类别"] = pdf_danger
                        if not normalized.get("危险品类别") and pdf_order_no in shipping_cache:
                            normalized["危险品类别"] = shipping_cache[pdf_order_no].get("danger", "")
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
                        parsed = _parse_pdf_docket(pdf_path)
                        normalized = FieldNormalizer.normalize(parsed)
                        pdf_order_no = normalized.get("order_no", "").strip()
                        if not pdf_order_no:
                            continue
                        if pdf_order_no in shipping_cache:
                            sc = shipping_cache[pdf_order_no]
                            normalized.setdefault("发运方式", sc.get("shipping", ""))
                        # 优先级：PDF 解析结果 > shipping 缓存
                        if not normalized.get("危险品类别"):
                            pdf_danger = parsed.get("pdf_danger", "")
                            if pdf_danger:
                                normalized["危险品类别"] = pdf_danger
                        if not normalized.get("危险品类别") and pdf_order_no in shipping_cache:
                            normalized["危险品类别"] = shipping_cache[pdf_order_no].get("danger", "")
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
                parsed = _parse_pdf_docket(pdf_path)
                normalized = FieldNormalizer.normalize(parsed)

                order_no = normalized.get("order_no", "").strip()
                # 严格校验：必须是合法的 8 位发货单号（或拆单格式），过滤 SO 单号等非法值
                if not order_no or not ContentParser._is_order_no(order_no.split('-')[0]):
                    logger.info(f"  → 跳过非法订单号 {order_no!r}（来自 {os.path.basename(pdf_path)}）")
                    continue

                # 过滤无效解析结果：必须至少有地址、重量或数量等核心字段
                has_core_field = bool(
                    normalized.get("address") or
                    normalized.get("weight") or
                    normalized.get("quantity") or
                    normalized.get("company_name")
                )
                if not has_core_field:
                    logger.info(f"  → 跳过空解析结果 {order_no}（来自 {filename}）")
                    continue

                if order_no in shipping_cache:
                    sc = shipping_cache[order_no]
                    normalized.setdefault("发运方式", sc.get("shipping", ""))

                # 优先级：PDF 解析结果 > shipping 缓存 > 留空
                # 1) 先检查 FieldNormalizer.normalize 是否已写入 pdf_danger
                # 2) 若无，则从 parsed 中获取 pdf_danger
                # 3) 最后才从 shipping 缓存中读取
                if not normalized.get("危险品类别"):
                    pdf_danger = parsed.get("pdf_danger", "")
                    if pdf_danger:
                        normalized["危险品类别"] = pdf_danger
                if not normalized.get("危险品类别") and order_no in shipping_cache:
                    normalized["危险品类别"] = shipping_cache[order_no].get("danger", "")
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
