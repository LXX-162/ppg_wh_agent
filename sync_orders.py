"""
sync_orders.py — 多维表写入入口

运行逻辑：
  1. 加载 pending_orders.json 暂存区
  2. 处理 已取消 的订单 → 按订单号匹配多维表记录，修改订单状态为"已取消"
  3. 处理 已更新 且已写入的订单（跨天）→ 按订单号匹配多维表记录，覆盖字段+状态=已更新
  4. 按业务日期过滤（pending + 今天/昨天的 已更新 → 写入，未来 → 暂存，其他 → 异常）
  5. 对待写入订单排序，输出 orders_YYYY-MM-DD.json
  6. 幂等写入：先删除多维表中今天的旧数据，再写入新数据
  7. 更新暂存区状态
"""

import sys
import os
import io
import json
import logging
from datetime import date, datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

from utils.cache_manager import PendingOrdersManager
from feishu.bitable import BitableClient

# 屏蔽底层日志
logging.getLogger("feishu.bitable").setLevel(logging.WARNING)
logging.getLogger("utils.cache_manager").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ── 飞书配置 ────────────────────────────────────────────────────────────────
APP_ID     = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
APP_TOKEN  = os.getenv("FEISHU_BITABLE_APP_TOKEN")
TABLE_ID   = os.getenv("FEISHU_BITABLE_TABLE_ID", "").split("&")[0].strip()

# ── 固定字段 ────────────────────────────────────────────────────────────────
CUSTOMER_NAME = "芜湖PPG"
ORIGIN_CITY   = "马鞍山库"


def parse_order_date(order: dict):
    """将订单中的 order_date 解析为 date 对象。"""
    raw = order.get("order_date", "")
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def order_to_feishu_record(order: dict, status: str = "正常") -> dict:
    """将订单字段映射为飞书多维表字段格式。"""
    # 重量：去掉 KG 后缀，转为数字
    weight_raw = order.get("weight", "0")
    weight_str = str(weight_raw).replace("KG", "").replace("kg", "").strip()
    if not weight_str:
        weight_str = "0"
    try:
        weight_num = float(weight_str)
    except (ValueError, TypeError):
        weight_num = 0.0

    # 数量：可能有小数（如 0.294），用 float 保留
    quantity_raw = order.get("quantity", "0")
    try:
        quantity = float(str(quantity_raw).strip())
    except (ValueError, TypeError):
        quantity = 0.0

    # 下单日期 → Unix 毫秒时间戳（飞书日期字段格式）
    order_date_ts = None
    order_date_str = order.get("order_date", "")
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(order_date_str.strip(), fmt)
            order_date_ts = int(dt.timestamp() * 1000)
            break
        except ValueError:
                        continue

    return {
        "客户名":   CUSTOMER_NAME,
        "单号":     order.get("order_no", ""),
        "订单状态": status,
        "下单日期": order_date_ts,
        "地址状态": order.get("address_exact_match", "模糊匹配"),
        "收货单位": order.get("receiver", ""),
        "收货公司名": order.get("company_name", ""),
        "收货地址": order.get("address", ""),
        "收货人":   order.get("contact", ""),
        "客户要求": order.get("requirement", ""),
        "数量":     quantity,
        "重量":     weight_num,
        "发运方式": order.get("发运方式", ""),
        "始发城市": ORIGIN_CITY,
        "到货城市": order.get("到货城市", ""),
        "到货省份": order.get("到货省份", ""),
        "产品特性": order.get("危险品类别", ""),
    }


def build_order_no_to_record_id(client, app_token, table_id):
    """
    拉取多维表所有记录，返回 { order_no: record_id } 映射。
    """
    all_records = client.get_records(app_token, table_id)
    mapping = {}
    for rec in all_records:
        fields = rec.get("fields", {})
        order_no = fields.get("单号", "")
        if order_no:
            mapping[order_no] = rec["record_id"]
    logger.info(f"多维表共 {len(all_records)} 条记录，建立 {len(mapping)} 个单号映射")
    return mapping


def sync():
    today = date.today()
    yesterday = today - timedelta(days=1)
    today_str = today.strftime("%Y/%m/%d")
    logger.info(f"=== 同步 {today_str}（今天+昨天） ===")

    client = BitableClient(APP_ID, APP_SECRET)

    # ── 1. 加载各种状态的订单 ────────────────────────────────────────
    all_pending   = PendingOrdersManager.get_by_status("pending")
    all_cancelled = PendingOrdersManager.get_by_status("已取消")
    all_updated   = PendingOrdersManager.get_by_status("已更新")
    # "拆单"状态的订单也需要写入（写入时状态设为"拆单"），但不需要跨天修改
    # 拆单的原单可能在"已更新"中，新单在"pending"中，也可能直接是"拆单"状态
    # 兼容直接设为"拆单"的情况
    all_split = PendingOrdersManager.get_by_status("拆单")

    # ── 2. 构建多维表订单号 → record_id 映射 ─────────────────────────
    order_to_record = build_order_no_to_record_id(client, APP_TOKEN, TABLE_ID)

    # ── 3. 处理 已取消 ──────────────────────────────────────────────
    #     修改多维表中对应记录的「订单状态」为"已取消"，其他字段不变
    cancel_updates = []
    for order in all_cancelled:
        order_no = order.get("order_no", "")
        record_id = order_to_record.get(order_no)
        if record_id:
            cancel_updates.append({
                "record_id": record_id,
                "fields": {"订单状态": "已取消"}
            })
            logger.info(f"[取消] {order_no} → 多维表状态改为 已取消")
        else:
            logger.info(f"[取消] {order_no} 不在多维表中，无需修改")

    if cancel_updates:
        done = client.batch_update_records(APP_TOKEN, TABLE_ID, cancel_updates)
        logger.info(f"已取消：成功修改 {done}/{len(cancel_updates)} 条")

    # ── 4. 处理 已更新（跨天修改——多维表中已有对应记录） ──────────────
    #     前提：已更新 且 业务日期 < 今天（表明是之前写入的，需要修改多维表）
    update_modifies = []
    for order in all_updated:
        biz_date = parse_order_date(order)
        order_no = order.get("order_no", "")
        record_id = order_to_record.get(order_no)
        if biz_date and biz_date < today and record_id:
            fields = order_to_feishu_record(order, status="已更新")
            update_modifies.append({
                "record_id": record_id,
                "fields": fields
            })
            logger.info(f"[更新] {order_no} 跨天修改多维表")

    if update_modifies:
        done = client.batch_update_records(APP_TOKEN, TABLE_ID, update_modifies)
        logger.info(f"已更新（跨天修改）：成功修改 {done}/{len(update_modifies)} 条")

    # ── 5. 按日期分组过滤 ────────────────────────────────────────────
    # 昨日写入：昨天 pending + 昨天 已更新（走写入，不是跨天修改）
    # 今日写入：今天 pending + 今天 已更新
    yesterday_orders = []
    today_orders     = []
    future_orders    = []
    anomalies        = []

    # 收集待写入订单
    # pending / 拆单 状态的订单直接加入
    all_candidates = list(all_pending) + list(all_split)
    # 已更新 状态的订单只在今天或昨天时才加入（跨天的已更新走跨天修改不走写入）
    for order in all_updated:
        biz_date = parse_order_date(order)
        if biz_date in (today, yesterday):
            all_candidates.append(order)

    for order in all_candidates:
        biz_date = parse_order_date(order)
        if biz_date is None:
            anomalies.append(order)
        elif biz_date == yesterday:
            yesterday_orders.append(order)
        elif biz_date == today:
            today_orders.append(order)
        elif biz_date > today:
            future_orders.append(order)
        else:
            anomalies.append(order)

    if anomalies:
        anomaly_nos = [o.get("order_no") for o in anomalies]
        PendingOrdersManager.mark_anomaly(anomaly_nos)

    if not yesterday_orders and not today_orders:
        logger.info(f"无待写入（昨日 0，今日 0，未来 {len(future_orders)}，异常 {len(anomalies)}），退出")
        return

    logger.info(f"待写入：昨日 {len(yesterday_orders)} 条，今日 {len(today_orders)} 条")

    # ── 6. 排序（按日期分别排序） ──────────────────────────────────────
    def sort_key(o):
        return (o.get("到货省份", ""), o.get("到货城市", ""),
                o.get("address", ""), o.get("order_no", ""))

    yesterday_orders.sort(key=sort_key)
    today_orders.sort(key=sort_key)

    # ── 7. 输出 orders.json（所有待写入按日期分组） ──────────────────
    json_path = os.path.join("output", f"orders_{today.isoformat()}.json")
    os.makedirs("output", exist_ok=True)
    try:
        all_sorted_orders = []
        for label, group in [("昨日", yesterday_orders), ("今日", today_orders)]:
            for o in group:
                fs = order_to_feishu_record(o)
                all_sorted_orders.append({
                    "单号":       o.get("order_no", ""),
                    "到货省份":   o.get("到货省份", ""),
                    "到货城市":   o.get("到货城市", ""),
                    "收货地址":   o.get("address", ""),
                    "收货单位":   o.get("receiver", ""),
                    "收货人":     o.get("contact", ""),
                    "重量":       fs.get("重量", ""),
                    "数量":       fs.get("数量", ""),
                    "发运方式":   o.get("发运方式", ""),
                    "危险品类别": o.get("危险品类别", ""),
                    "客户要求":   o.get("requirement", ""),
                    "日期":       label,
                })
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_sorted_orders, f, ensure_ascii=False, indent=2)
        logger.info(f"已输出 {json_path}（{len(all_sorted_orders)} 条）")
    except Exception as e:
        logger.error(f"输出 orders.json 失败: {e}")

    # ── 8. 写入飞书多维表，按日期分别写入 ────────────────────────────
    #     规则：昨日订单直接写入（多维表中没有旧数据需删除）
    #           今日订单先删今日旧数据再写入（幂等保证）
    all_synced_nos = []
    BATCH_SIZE = 500

    # 8a. 写入昨日订单（直接写入，不删数据）
    if yesterday_orders:
        yesterday_records = []
        for o in yesterday_orders:
            s = o.get("sync_status", "")
            if s == "拆单":
                status = "拆单"
            elif s == "已更新":
                status = "已更新"
            else:
                status = "正常"
            yesterday_records.append(order_to_feishu_record(o, status=status))

        y_success = 0
        for i in range(0, len(yesterday_records), BATCH_SIZE):
            batch = yesterday_records[i: i + BATCH_SIZE]
            ok = client.write_records(APP_TOKEN, TABLE_ID, batch)
            if ok:
                y_success += len(batch)
            else:
                logger.error(f"昨日订单第 {i // BATCH_SIZE + 1} 批写入失败，已中止")
                break

        if y_success == len(yesterday_records):
            all_synced_nos.extend([o.get("order_no") for o in yesterday_orders])
            logger.info(f"昨日写入完成：{y_success} 条")
        else:
            logger.warning(f"昨日部分写入失败（{y_success}/{len(yesterday_records)}），暂留待下次重试")

    # 8b. 写入今日订单（先删今日旧数据，再写入）
    if today_orders:
        client.delete_records_by_date(APP_TOKEN, TABLE_ID, today_str)

        today_records = []
        for o in today_orders:
            s = o.get("sync_status", "")
            if s == "拆单":
                status = "拆单"
            elif s == "已更新":
                status = "已更新"
            else:
                status = "正常"
            today_records.append(order_to_feishu_record(o, status=status))

        t_success = 0
        for i in range(0, len(today_records), BATCH_SIZE):
            batch = today_records[i: i + BATCH_SIZE]
            ok = client.write_records(APP_TOKEN, TABLE_ID, batch)
            if ok:
                t_success += len(batch)
            else:
                logger.error(f"今日订单第 {i // BATCH_SIZE + 1} 批写入失败，已中止")
                break

        if t_success == len(today_records):
            all_synced_nos.extend([o.get("order_no") for o in today_orders])
            logger.info(f"今日写入完成：{t_success} 条")
        else:
            logger.warning(f"今日部分写入失败（{t_success}/{len(today_records)}），暂留待下次重试")

    # ── 9. 更新暂存区状态 ────────────────────────────────────────────
    if all_synced_nos:
        PendingOrdersManager.mark_synced(all_synced_nos, synced_at=datetime.now().isoformat())
        logger.info(f"共标记 synced：{len(all_synced_nos)} 条")
    else:
        logger.warning("本次无订单成功写入，暂存区状态未更新")


if __name__ == "__main__":
    sync()
    sync()
