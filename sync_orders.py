"""
sync_orders.py — 多维表写入入口

运行逻辑：
  1. 加载 pending_orders.json 暂存区
  2. 处理 已取消 的订单 → 按订单号匹配多维表记录，修改订单状态为"已取消"
  3. 处理 已更新 且已写入的订单（跨天）→ 按订单号匹配多维表记录，覆盖字段+状态=已更新
  4. 所有 pending/拆单/已更新 订单不区分日期，全部写入（不再过滤今天/昨天）
  5. 对待写入订单排序，输出 orders_YYYY-MM-DD.json
  6. 直接写入，不删除旧数据（由调用方负责幂等）
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
    today_str = today.strftime("%Y/%m/%d")
    logger.info(f"=== 同步写入（忽略日期，全部 pending 订单写入） ===")

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

    # ── 4. 处理 已更新（改单——多维表中已有对应记录） ──────────────────
    #     只要多维表中有对应记录，不区分日期，一律覆盖内容＋状态=已更新
    update_modifies = []
    for order in all_updated:
        order_no = order.get("order_no", "")
        record_id = order_to_record.get(order_no)
        if record_id:
            fields = order_to_feishu_record(order, status="已更新")
            update_modifies.append({
                "record_id": record_id,
                "fields": fields
            })
            logger.info(f"[更新] {order_no} 覆盖多维表已有记录")

    if update_modifies:
        done = client.batch_update_records(APP_TOKEN, TABLE_ID, update_modifies)
        logger.info(f"已更新（改单覆盖）：成功修改 {done}/{len(update_modifies)} 条")

    # ── 5. 收集所有待写入订单（不区分日期）────────────────────────────
    # pending / 拆单 状态的订单直接加入
    all_candidates = list(all_pending) + list(all_split)
    # 已更新 状态：跨天修改（多维表中有记录）已在步骤4处理；
    # 这里把 所有已更新 也加入写入候选（若多维表无对应记录则需新写入）
    for order in all_updated:
        order_no = order.get("order_no", "")
        if order_no not in order_to_record:
            all_candidates.append(order)

    # 过滤无法解析日期的异常订单
    anomalies     = [o for o in all_candidates if parse_order_date(o) is None]
    write_orders  = [o for o in all_candidates if parse_order_date(o) is not None]

    if anomalies:
        anomaly_nos = [o.get("order_no") for o in anomalies]
        PendingOrdersManager.mark_anomaly(anomaly_nos)
        logger.warning(f"无法解析日期的异常订单 {len(anomalies)} 条，已标记 anomaly")

    if not write_orders:
        logger.info(f"无待写入订单（异常 {len(anomalies)} 条），退出")
        return

    logger.info(f"待写入：共 {len(write_orders)} 条（忽略日期）")

    # ── 6. 排序 ──────────────────────────────────────────────────────
    def sort_key(o):
        return (o.get("到货省份", ""), o.get("到货城市", ""),
                o.get("address", ""), o.get("order_no", ""))

    write_orders.sort(key=sort_key)

    # ── 7. 输出 orders.json ──────────────────────────────────────────
    json_path = os.path.join("output", f"orders_{today.isoformat()}.json")
    os.makedirs("output", exist_ok=True)
    try:
        all_sorted_orders = []
        for o in write_orders:
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
                "下单日期":   o.get("order_date", ""),
            })
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_sorted_orders, f, ensure_ascii=False, indent=2)
        logger.info(f"已输出 {json_path}（{len(all_sorted_orders)} 条）")
    except Exception as e:
        logger.error(f"输出 orders.json 失败: {e}")

    # ── 8. 写入飞书多维表（直接写入，不区分日期） ────────────────────
    all_synced_nos = []
    BATCH_SIZE = 500

    write_records = []
    for o in write_orders:
        s = o.get("sync_status", "")
        if s == "拆单":
            status = "拆单"
        elif s == "已更新":
            status = "已更新"
        else:
            status = "正常"
        write_records.append(order_to_feishu_record(o, status=status))

    success_total = 0
    for i in range(0, len(write_records), BATCH_SIZE):
        batch = write_records[i: i + BATCH_SIZE]
        ok = client.write_records(APP_TOKEN, TABLE_ID, batch)
        if ok:
            success_total += len(batch)
        else:
            logger.error(f"第 {i // BATCH_SIZE + 1} 批写入失败，已中止")
            break

    if success_total == len(write_records):
        all_synced_nos.extend([o.get("order_no") for o in write_orders])
        logger.info(f"写入完成：{success_total} 条")
    else:
        logger.warning(f"部分写入失败（{success_total}/{len(write_records)}），暂留待下次重试")

    # ── 9. 更新暂存区状态 ────────────────────────────────────────────
    if all_synced_nos:
        PendingOrdersManager.mark_synced(all_synced_nos, synced_at=datetime.now().isoformat())
        logger.info(f"共标记 synced：{len(all_synced_nos)} 条")
    else:
        logger.warning("本次无订单成功写入，暂存区状态未更新")


if __name__ == "__main__":
    sync()
