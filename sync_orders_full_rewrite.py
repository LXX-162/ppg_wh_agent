"""
sync_orders_full_rewrite.py — 临时：全量重写，不删数据
多维表清空后，将所有 pending 订单不分日期全部写入。
"""

import sys
import os
import io
import json
import logging
from datetime import date, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from utils.cache_manager import PendingOrdersManager
from feishu.bitable import BitableClient

logging.getLogger("feishu.bitable").setLevel(logging.WARNING)
logging.getLogger("utils.cache_manager").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

APP_ID     = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
APP_TOKEN  = os.getenv("FEISHU_BITABLE_APP_TOKEN")
TABLE_ID   = os.getenv("FEISHU_BITABLE_TABLE_ID", "").split("&")[0].strip()

CUSTOMER_NAME = "芜湖PPG"
ORIGIN_CITY   = "马鞍山库"


def parse_order_date(order: dict):
    raw = order.get("order_date", "")
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def order_to_feishu_record(order: dict, status: str = "正常") -> dict:
    weight_raw = order.get("weight", "0")
    weight_str = str(weight_raw).replace("KG", "").replace("kg", "").strip()
    if not weight_str:
        weight_str = "0"
    try:
        weight_num = float(weight_str)
    except (ValueError, TypeError):
        weight_num = 0.0

    quantity_raw = order.get("quantity", "0")
    try:
        quantity = float(str(quantity_raw).strip())
    except (ValueError, TypeError):
        quantity = 0.0

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


def sync():
    today = date.today()
    logger.info(f"=== 全量重写 {today} ===")

    client = BitableClient(APP_ID, APP_SECRET)

    all_pending = PendingOrdersManager.get_by_status("pending")
    if not all_pending:
        logger.info("暂存区无待同步订单，退出")
        return

    # 全部 pending 不分日期，全部写入
    to_write = list(all_pending)

    def sort_key(o):
        d = parse_order_date(o)
        # 将 None 日期排到最后
        date_key = d.isoformat() if d else "9999-99-99"
        return (
            date_key,
            o.get("到货省份", ""),
            o.get("到货城市", ""),
            o.get("address", ""),
            o.get("order_no", ""),
        )

    to_write.sort(key=sort_key)

    # 输出 orders.json
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
            "重量":       order_to_feishu_record(o).get("重量", ""),
            "数量":       order_to_feishu_record(o).get("数量", ""),
            "发运方式":   o.get("发运方式", ""),
            "危险品类别": o.get("危险品类别", ""),
            "客户要求":   o.get("requirement", ""),
        } for o in to_write]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sorted_orders, f, ensure_ascii=False, indent=2)
        logger.info(f"已输出 {json_path}（{len(sorted_orders)} 条）")
    except Exception as e:
        logger.error(f"输出 orders.json 失败: {e}")

    # 不删数据，直接写入
    records = [order_to_feishu_record(o, status="正常") for o in to_write]
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

    if success_total == len(records):
        synced_nos = [o.get("order_no") for o in to_write]
        PendingOrdersManager.mark_synced(synced_nos, synced_at=datetime.now().isoformat())
        logger.info(f"写入完成：{success_total} 条")
    else:
        logger.warning(f"部分写入失败（{success_total}/{len(records)}），暂存区未更新，下次重试")


if __name__ == "__main__":
    sync()
