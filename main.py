import sys
import os
import subprocess

# ── 第一步：确保依赖已安装（在所有其他导入之前） ──────────────────
def ensure_dependencies():
    """检查并自动安装 jionlp"""
    def _print(msg):
        """安全输出，兼容 Windows GBK 终端（utf-8 重定向尚未生效时）。"""
        try:
            print(msg)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((msg + "\n").encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()

    try:
        import jionlp
        _print("[OK] jionlp installed")
        return True
    except ImportError:
        _print("[WARN] jionlp not found, installing...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "jionlp",
                "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple",
                "--timeout", "120",
                "--no-cache-dir"
            ])
            _print("[OK] jionlp installed successfully")
            return True
        except Exception as e:
            _print(f"[ERR] install failed: {e}")
            # 尝试备用源
            try:
                _print("[RETRY] trying mirror...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "jionlp",
                    "--index-url", "https://mirrors.aliyun.com/pypi/simple/",
                    "--timeout", "120"
                ])
                _print("[OK] jionlp installed via mirror")
                return True
            except Exception as e2:
                _print(f"[ERR] mirror install also failed: {e2}")
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
    logger.info("[1/4] 加载本地缓存...")
    seen_uids = SeenMailsManager.load()
    shipping_cache = CacheManager.load_cache()
    logger.info(f"  已读邮件记录: {len(seen_uids)} 条，shipping 缓存: {len(shipping_cache)} 条")
    logger.info("[2/4] 初始化邮件连接...")
    reader = MailReader()

    try:
        # ── 2. 拉取未读邮件（带重试机制） ────────────────────────────
        # 向服务器搜索全部 UID（只返回 ID 列表，很快），在客户端用 seen_uids 过滤，
        # 只对真正未读的 UID 发起 FETCH（下载邮件正文）。
        # 无需限制日期范围，历史邮件第一次处理后即标记 seen，后续运行自动跳过。
        fetch_ok = False
        mails = []
        logger.info("[3/4] 拉取邮件（IMAP 连接中，请稍候...）")
        for attempt in range(3):
            try:
                mails = reader.fetch_recent(
                    limit=None,
                    search_criteria='ALL',
                    skip_uids=seen_uids,   # 客户端过滤，只下载未读
                )
                fetch_ok = True
                break
            except Exception as e:
                logger.warning(f"拉取邮件第 {attempt + 1} 次失败: {e}")
                reader.disconnect()
                if attempt < 2:
                    logger.info(f"  3 秒后重试（第 {attempt + 2} 次）...")
                    time.sleep(3)

        if not fetch_ok:
            logger.error("多次尝试后仍无法拉取邮件，退出")
            return

        if not mails:
            logger.info("没有新的未读邮件，退出")
            return

        logger.info(f"[4/4] 本次需处理未读邮件: {len(mails)} 封")

        # ── 3. 统一处理未读邮件（一遍完成全部任务） ─────────────────
        # 每封邮件可能同时触发多个动作（更新 shipping 缓存 / 取消指令 / PDF解析），
        # 互不干扰。处理完即标记 seen，下次运行不重复处理。
        #
        # add_orders() 内部自动判断写入状态：
        #   - order_no 不存在 → pending（新单）
        #   - 已存在且 synced，内容有变化 → 已更新（改单，触发重写飞书）
        #   - 已存在且 pending → 覆盖（用最新 PDF 数据）
        #   - 已存在且 已取消 → 重新激活为 pending（见 cache_manager.py）
        shipping_updated = False
        all_new_orders   = []   # 所有解析到的订单，最后统一写入 pending
        cancel_orders    = set()

        for m in mails:
            uid       = m["uid"]
            msg       = m["message"]
            mail_type = MailFilter.get_type(m)
            sender    = m.get("sender", "").lower()
            subject   = m.get("subject", "") or str(msg.get("Subject", ""))
            body      = _extract_body(msg)
            body_s    = body.strip()
            body_lo   = body_s.lower()

            is_wenjuan = ("wenjuan" in sender or
                          ("juan" in sender and "wen" in sender))

            # ── A. 更新 shipping 缓存 ─────────────────────────────────
            if is_wenjuan:
                # wenjuan：正文为空且有 PDF 时，从主题提取发运方式
                has_pdf_attach = msg.is_multipart() and any(
                    (part.get_filename() or "").lower().endswith(".pdf")
                    for part in msg.walk()
                )
                if not body_s and has_pdf_attach:
                    shipping_kw = next(
                        (kw for kw in ["保温车", "包车", "零担", "自提"] if kw in subject),
                        ""
                    )
                    if shipping_kw:
                        order_nos = set(re.findall(r'(11\d{6,8})', subject))
                        for part in msg.walk():
                            fn = part.get_filename() or ""
                            order_nos.update(re.findall(r'(11\d{6,8})', fn))
                        for on in order_nos:
                            cur = shipping_cache.get(on, {})
                            if cur.get("shipping") != shipping_kw:
                                shipping_cache[on] = {
                                    "shipping": shipping_kw,
                                    "danger": cur.get("danger", ""),
                                }
                                shipping_updated = True

            elif mail_type == "SHIPPING_INFO" and body_s:
                # 其他发件人的 SHIPPING_INFO 邮件：首次写入后不覆盖
                new_data = ContentParser.parse_shipping_mail(subject, body_s)
                for order_no, info in (new_data or {}).items():
                    if order_no not in shipping_cache:
                        shipping_cache[order_no] = info
                        shipping_updated = True

            # ── B. 取消指令 ──────────────────────────────────────────
            is_cancel = any(kw in body_lo for kw in ["停止", "作废", "不用发", "取消"])
            if is_cancel:
                found = set(re.findall(r'(11\d{6,8})', body_s))
                found.update(re.findall(r'(11\d{6,8})', subject))
                if found:
                    logger.info(f"[指令-取消] UID={uid}: {subject[:60]}")
                    cancel_orders.update(found)
                    for on in found:
                        logger.info(f"  → 取消订单 {on}")

            # ── C. PDF 解析 ──────────────────────────────────────────
            # 触发条件：PDF_ORDER 发件人 / 含"更新/以此为准"关键词 / 含"拆"关键词
            should_parse = (
                mail_type == "PDF_ORDER"
                or any(kw in body_lo for kw in ["更新", "以此为准", "重新提供"])
                or "拆" in body_s or "拆" in subject
            )
            if should_parse:
                saved_pdfs = save_attachments(uid, msg)
                pdf_files = [p for p in saved_pdfs if p.lower().endswith('.pdf')]

                if pdf_files:
                    is_split = (("拆" in body_s or "拆" in subject)
                                and len(pdf_files) >= 2)
                    if is_split:
                        logger.info(f"[指令-拆单] UID={uid}: {subject[:60]}")
                    else:
                        logger.info(f"[PDF解析] UID={uid}: {subject[:60]}")

                    parsed_list = []  # [(order_no, normalized_dict), ...]
                    for pdf_path in pdf_files:
                        parsed = _parse_pdf_docket(pdf_path)
                        normalized = FieldNormalizer.normalize(parsed)
                        order_no = normalized.get("order_no", "").strip()

                        if not order_no or not ContentParser._is_order_no(
                                order_no.split('-')[0]):
                            logger.info(f"  → 跳过非法订单号 {order_no!r}"
                                        f"（{os.path.basename(pdf_path)}）")
                            continue

                        has_core = bool(
                            normalized.get("address") or normalized.get("weight")
                            or normalized.get("quantity") or normalized.get("company_name")
                        )
                        if not has_core:
                            logger.info(f"  → 跳过空解析结果 {order_no}"
                                        f"（{os.path.basename(pdf_path)}）")
                            continue

                        # 合并 shipping 缓存
                        if order_no in shipping_cache:
                            sc = shipping_cache[order_no]
                            normalized.setdefault("发运方式", sc.get("shipping", ""))
                        if not normalized.get("危险品类别"):
                            pdf_danger = parsed.get("pdf_danger", "")
                            if pdf_danger:
                                normalized["危险品类别"] = pdf_danger
                        if not normalized.get("危险品类别") and order_no in shipping_cache:
                            normalized["危险品类别"] = shipping_cache[order_no].get("danger", "")

                        parsed_list.append((order_no, normalized))

                    # 拆单：第一个为原单，第二个为子单
                    if is_split and len(parsed_list) >= 2:
                        orig_no, orig_data = parsed_list[0]
                        orig_data["sync_status"] = "拆单"
                        all_new_orders.append(orig_data)
                        logger.info(f"  → 原单 {orig_no}（拆单）")

                        new_no, new_data = parsed_list[1]
                        if new_no == orig_no:
                            new_no = f"{orig_no}-1"
                            new_data["order_no"] = new_no
                        new_data["sync_status"] = "拆单"
                        all_new_orders.append(new_data)
                        logger.info(f"  → 子单 {new_no}（拆单）")
                    else:
                        for order_no, normalized in parsed_list:
                            all_new_orders.append(normalized)
                            logger.info(f"  → 解析订单 {order_no}")

            # ── 标记已读 ─────────────────────────────────────────────
            seen_uids.add(str(uid))

        # ── 4. 执行取消指令 ──────────────────────────────────────────
        if cancel_orders:
            pending = PendingOrdersManager.load_pending()
            any_change = False
            for on in cancel_orders:
                if on in pending:
                    pending[on]["sync_status"] = "已取消"
                    pending[on]["synced_at"] = None
                    any_change = True
                    logger.info(f"  → [取消] 订单 {on} 已标记为 已取消")
                else:
                    logger.info(f"  → [取消] 订单 {on} 不在暂存区，跳过")
            if any_change:
                PendingOrdersManager.save_pending(pending)
            logger.info(f"[取消] 共处理 {len(cancel_orders)} 条")

        # ── 5. 写入新订单/更新订单 ────────────────────────────────────
        if all_new_orders:
            PendingOrdersManager.add_orders(all_new_orders)
            logger.info(f"[写入] 共处理 {len(all_new_orders)} 条订单记录")
        else:
            logger.info("本次运行未发现新订单")

        # ── 6. 保存 shipping 缓存 ─────────────────────────────────────
        if shipping_updated:
            today = datetime.today().strftime("%Y-%m-%d")
            CacheManager.save_cache(shipping_cache, date_str=today)

        # ── 7. 持久化已读记录 ─────────────────────────────────────────
        SeenMailsManager.save(seen_uids)

        # ── 8. 输出摘要 ───────────────────────────────────────────────
        pending_count = len(PendingOrdersManager.get_by_status("pending"))
        updated_count = len(PendingOrdersManager.get_by_status("已更新"))
        logger.info(f"当前暂存区: pending={pending_count} 条，已更新={updated_count} 条")

    except Exception as e:
        logger.error(f"执行异常: {e}", exc_info=True)
    finally:
        reader.disconnect()


if __name__ == "__main__":
    main()
