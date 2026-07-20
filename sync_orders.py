"""
sync_orders.py — 多维表写入入口
由飞书 Aily 定时触发，负责将暂存区中今天的订单写入飞书多维表。

运行逻辑：
  1. 加载 pending_orders.json 暂存区
  2. 按业务日期（order_date）分三类：
       == 今天 → to_write（待写入）
       >  今天 → to_defer（暂存，等待）
       <  今天 → anomalies（异常告警，跳过）
  3. 对 to_write 按省份 → 城市 → 收货地址排序
  4. 幂等写入：先删除多维表中今天的旧数据，再写入新数据
  5. 更新暂存区状态（synced / anomaly）
"""

import sys
import os
import io
import logging
from datetime import date, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from utils.cache_manager import PendingOrdersManager
from feishu.bitable import BitableClient

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
    """
    将订单中的 order_date 字段解析为 date 对象。
    支持格式：YYYY/M/D、YYYY/MM/DD、YYYY-MM-DD。
    解析失败返回 None。
    """
    raw = order.get("order_date", "")
    for fmt in ("%Y/%m/%d", "%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    logger.warning(f"[{order.get('order_no')}] 无法解析业务日期: {raw!r}")
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
        "地址状态": order.get("address_exact_match", "N"),
        "收货单位": order.get("receiver", ""),
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
    logger.info(f"=== 开始同步，业务日期：{today_str} ===")

    # ── 1. 加载暂存区 ────────────────────────────────────────────────
    all_pending = PendingOrdersManager.get_by_status("pending")
    logger.info(f"暂存区 pending 订单数：{len(all_pending)}")

    if not all_pending:
        logger.info("没有待同步订单，退出")
        return

    # ── 2. 按业务日期过滤 ────────────────────────────────────────────
    to_write   = []   # 今天
    to_defer   = []   # 未来（继续暂存）
    anomalies  = []   # 过去（异常）

    for order in all_pending:
        biz_date = parse_order_date(order)
        if biz_date is None:
            anomalies.append(order)
        elif biz_date == today:
            to_write.append(order)
        elif biz_date > today:
            to_defer.append(order)
        else:  # biz_date < today
            anomalies.append(order)

    logger.info(f"今日待写入：{len(to_write)} 条 | 未来暂存：{len(to_defer)} 条 | 异常：{len(anomalies)} 条")

    # 告警：异常订单
    if anomalies:
        anomaly_nos = [o.get("order_no") for o in anomalies]
        logger.warning(f"⚠️  以下订单业务日期早于今天，将跳过写入: {anomaly_nos}")
        PendingOrdersManager.mark_anomaly(anomaly_nos)

    if not to_write:
        logger.info("今日无待写入订单，退出")
        return

    # ── 3. 排序：省份 → 城市 → 收货地址 ────────────────────────────
    to_write.sort(key=lambda o: (
        o.get("到货省份", ""),
        o.get("到货城市", ""),
        o.get("address", "")
    ))
    logger.info("排序完成（省份 → 城市 → 地址）")

    # ── 4. 幂等写入飞书多维表 ────────────────────────────────────────
    client = BitableClient(APP_ID, APP_SECRET)

    # 4a. 删除多维表中今天的旧数据
    logger.info(f"正在删除多维表中 {today_str} 的旧记录...")
    deleted = client.delete_records_by_date(APP_TOKEN, TABLE_ID, today_str)
    logger.info(f"删除完成，共删除 {deleted} 条旧记录")

    # 4b. 写入新数据
    records = [order_to_feishu_record(o) for o in to_write]
    BATCH_SIZE = 500
    success_total = 0

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i: i + BATCH_SIZE]
        logger.info(f"写入第 {i + 1}～{i + len(batch)} 条记录...")
        ok = client.write_records(APP_TOKEN, TABLE_ID, batch)
        if ok:
            success_total += len(batch)
        else:
            logger.error(f"第 {i + 1} 批写入失败，已中止")
            break

    logger.info(f"写入完成：{success_total}/{len(records)} 条成功")

    # ── 5. 更新暂存区状态 ────────────────────────────────────────────
    if success_total == len(records):
        synced_nos = [o.get("order_no") for o in to_write]
        now_str = datetime.now().isoformat()
        PendingOrdersManager.mark_synced(synced_nos, synced_at=now_str)
        logger.info(f"=== 同步成功，共写入 {success_total} 条记录 ===")
    else:
        logger.warning("部分记录写入失败，暂存区状态未更新，下次触发时将重试")

    logger.info(f"未来日期订单：{len(to_defer)} 条，继续留存 pending 等待处理")


if __name__ == "__main__":
    sync()
