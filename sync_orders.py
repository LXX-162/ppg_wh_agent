"""
sync_orders.py — 多维表写入入口
将暂存区中今天的订单写入飞书多维表，同时输出排序后的 orders.json。

运行逻辑：
  1. 加载 pending_orders.json 暂存区
  2. 按业务日期（order_date）分三类：
       == 今天 → to_write（待写入）
       >  今天 → to_defer（暂存，等待）
       <  今天 → anomalies（异常告警，跳过）
  3. 对 to_write 按省份 → 城市 → 地址 → 订单号排序
  4. 输出排序后的 orders_YYYY-MM-DD.json（供发货拼单参考）
  5. 幂等写入：先删除多维表中今天的旧数据，再写入新数据
  6. 更新暂存区状态（synced / anomaly）
"""

import sys
import os
import io
import json
import logging
from datetime import date, datetime

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
ORDER_STATUS  = "正常"


def parse_order_date(order: dict):
    """将订单中的 order_date 解析为 date 对象。"""
    raw = order.get("order_date", "")
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def order_to_feishu_record(order: dict) -> dict:
    """将订单字段映射为飞书多维表字段格式。"""
    # 重量
    weight_raw = order.get("weight", "0")
    try:
        weight = float(str(weight_raw).replace("KG", "").replace("kg", "").strip())
    except ValueError:
        weight = 0.0

    # 数量
    try:
        quantity = int(order.get("quantity", 0))
    except (ValueError, TypeError):
        quantity = 0

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
        "订单状态": ORDER_STATUS,
        "下单日期": order_date_ts,
        "地址状态": order.get("address_exact_match", "模糊匹配"),
        "收货单位": order.get("receiver", ""),
        "收货公司名": order.get("company_name", ""),
        "收货地址": order.get("address", ""),
        "收货人":   order.get("contact", ""),
        "客户要求": order.get("requirement", ""),
        "数量":     quantity,
        "重量":     weight,
        "发运方式": order.get("发运方式", ""),
        "始发城市": ORIGIN_CITY,
        "到货城市": order.get("到货城市", ""),
        "到货省份": order.get("到货省份", ""),
        "产品特性": order.get("危险品类别", ""),
    }


def sync():
    today = date.today()
    today_str = today.strftime("%Y/%m/%d")
    logger.info(f"=== 同步 {today_str} ===")

    # ── 1. 加载暂存区 ────────────────────────────────────────────────
    all_pending = PendingOrdersManager.get_by_status("pending")
    if not all_pending:
        logger.info("暂存区无待同步订单，退出")
        return

    # ── 2. 按业务日期过滤 ────────────────────────────────────────────
    to_write  = []
    to_defer  = []
    anomalies = []

    for order in all_pending:
        biz_date = parse_order_date(order)
        if biz_date is None:
            anomalies.append(order)
        elif biz_date == today:
            to_write.append(order)
        elif biz_date > today:
            to_defer.append(order)
        else:
            anomalies.append(order)

    if anomalies:
        anomaly_nos = [o.get("order_no") for o in anomalies]
        PendingOrdersManager.mark_anomaly(anomaly_nos)

    if not to_write:
        logger.info(f"今日无待写入（待写入 {len(to_write)}，未来 {len(to_defer)}，异常 {len(anomalies)}），退出")
        return

    logger.info(f"待写入 {len(to_write)} 条（未来 {len(to_defer)}，异常 {len(anomalies)}）")

    # ── 3. 排序 ──────────────────────────────────────────────────────
    to_write.sort(key=lambda o: (
        o.get("到货省份", ""),
        o.get("到货城市", ""),
        o.get("address", ""),
        o.get("order_no", "")
    ))

    # ── 4. 输出 orders.json ─────────────────────────────────────────
    json_path = os.path.join("output", f"orders_{today.isoformat()}.json")
    os.makedirs("output", exist_ok=True)
    try:
        sorted_orders = [{
            "单号":       o.get("order_no", ""),
            "到货省份":   o.get("到货省份", ""),
            "到货城市":   o.get("到货城市", ""),
            "收货地址":   o.get("address", ""),
            "收货单位":   o.get("receiver", ""),
            "收货人":     o.get("contact", ""),
            "重量":       o.get("weight", ""),
            "数量":       o.get("quantity", ""),
            "发运方式":   o.get("发运方式", ""),
            "危险品类别": o.get("危险品类别", ""),
            "客户要求":   o.get("requirement", ""),
        } for o in to_write]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sorted_orders, f, ensure_ascii=False, indent=2)
        logger.info(f"已输出 {json_path}（{len(sorted_orders)} 条）")
    except Exception as e:
        logger.error(f"输出 orders.json 失败: {e}")

    # ── 5. 幂等写入飞书多维表 ────────────────────────────────────────
    client = BitableClient(APP_ID, APP_SECRET)

    deleted = client.delete_records_by_date(APP_TOKEN, TABLE_ID, today_str)

    records = [order_to_feishu_record(o) for o in to_write]
    success_total = 0
    BATCH_SIZE = 500

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i: i + BATCH_SIZE]
        ok = client.write_records(APP_TOKEN, TABLE_ID, batch)
        if ok:
            success_total += len(batch)
        else:
            logger.error(f"第 {i // BATCH_SIZE + 1} 批写入失败，已中止")
            break

    # ── 6. 更新暂存区状态 ────────────────────────────────────────────
    if success_total == len(records):
        synced_nos = [o.get("order_no") for o in to_write]
        PendingOrdersManager.mark_synced(synced_nos, synced_at=datetime.now().isoformat())
        logger.info(f"写入完成：{success_total} 条")
    else:
        logger.warning(f"部分写入失败（{success_total}/{len(records)}），暂存区未更新，下次重试")


if __name__ == "__main__":
    sync()
