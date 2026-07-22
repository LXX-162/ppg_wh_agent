"""
write_company_name.py — 补写「收货公司名」到飞书多维表

策略：
  1. 从 output/test_7_14_orders.json 读取订单，建立 order_no → company_name 索引
  2. 拉取飞书多维表中所有现有记录
  3. 按「单号」字段匹配，找出需要补写公司名的记录
  4. 批量调用 batch_update 接口更新「收货公司名」字段
"""

import sys
import io
import os
import json
import logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from feishu.bitable import BitableClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────────────────────────
INPUT_JSON = os.path.join(os.path.dirname(__file__), "output", "test_7_14_orders.json")

APP_ID     = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
APP_TOKEN  = os.getenv("FEISHU_BITABLE_APP_TOKEN")
TABLE_ID   = os.getenv("FEISHU_BITABLE_TABLE_ID", "").split("&")[0].strip()


def main():
    # 1. 读取本地 JSON，建立单号 → 公司名 映射
    with open(INPUT_JSON, encoding="utf-8") as f:
        all_orders = json.load(f)
    logger.info(f"读取到 {len(all_orders)} 条订单")

    company_map = {}
    for o in all_orders:
        order_no = str(o.get("order_no", "")).strip()
        company_name = o.get("company_name", "").strip()
        if order_no and company_name:
            company_map[order_no] = company_name

    logger.info(f"有公司名的订单数: {len(company_map)}")

    # 2. 拉取飞书多维表中所有记录
    client = BitableClient(APP_ID, APP_SECRET)
    logger.info("正在拉取飞书多维表记录…")
    feishu_records = client.get_records(APP_TOKEN, TABLE_ID)
    logger.info(f"飞书共有 {len(feishu_records)} 条记录")

    if not feishu_records:
        logger.warning("飞书中没有记录，请先写入数据后再运行本脚本")
        return

    # 3. 按单号匹配，构建更新列表
    updates = []
    no_match = []
    for rec in feishu_records:
        record_id = rec.get("record_id", "")
        fields = rec.get("fields", {})
        # 飞书中单号字段可能是字符串或数字
        order_no = str(fields.get("单号", "")).strip()
        if order_no in company_map:
            updates.append({
                "record_id": record_id,
                "fields": {
                    "收货公司名": company_map[order_no]
                }
            })
        else:
            no_match.append(order_no)

    logger.info(f"匹配到 {len(updates)} 条需要更新的记录")
    if no_match:
        logger.warning(f"飞书中有 {len(no_match)} 条记录在本地 JSON 中找不到匹配（单号: {no_match[:5]}...）")

    if not updates:
        logger.info("没有需要更新的记录，退出")
        return

    # 预览前 3 条
    logger.info("=== 前 3 条更新预览 ===")
    for u in updates[:3]:
        print(json.dumps(u, ensure_ascii=False, indent=2))

    # 4. 批量更新
    success = client.batch_update_records(APP_TOKEN, TABLE_ID, updates)
    logger.info(f"✅ 批量更新完成：{success}/{len(updates)} 条成功")


if __name__ == "__main__":
    main()
