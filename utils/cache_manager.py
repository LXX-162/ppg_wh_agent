import os
import json
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join("output", "cache")


class CacheManager:
    """
    管理 shipping 缓存（发运方式/危险品类别）。
    每天独立一个文件：output/cache/shipping_YYYY-MM-DD.json
    同时维护一个 shipping_latest.json 作为全量合并视图（历史累积）。
    """

    @staticmethod
    def _shipping_path(date_str: str = None) -> str:
        """返回指定日期的 shipping 文件路径。date_str 格式 YYYY-MM-DD，默认今天。"""
        if not date_str:
            date_str = date.today().isoformat()
        return os.path.join(CACHE_DIR, f"shipping_{date_str}.json")

    @staticmethod
    def _shipping_all_path() -> str:
        return os.path.join(CACHE_DIR, "shipping_all.json")

    @classmethod
    def load_cache(cls, date_str: str = None) -> dict:
        """
        加载指定日期的 shipping 缓存。
        如果 date_str 为 None，返回全量历史合并缓存（shipping_all.json）。
        """
        if date_str:
            path = cls._shipping_path(date_str)
        else:
            path = cls._shipping_all_path()

        if not os.path.exists(path):
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 shipping 缓存失败 {path}: {e}")
            return {}

    @classmethod
    def save_cache(cls, data: dict, date_str: str = None):
        """
        保存 shipping 缓存。
        - 写入指定日期文件（默认今天）
        - 同时更新全量合并文件 shipping_all.json
        """
        os.makedirs(CACHE_DIR, exist_ok=True)

        if not date_str:
            date_str = date.today().isoformat()

        # 1. 写入日期文件
        day_path = cls._shipping_path(date_str)
        try:
            with open(day_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"成功保存 shipping 缓存至 {day_path}")
        except Exception as e:
            logger.error(f"保存 shipping 缓存失败 {day_path}: {e}")

        # 2. 更新全量合并文件（merge，不会删除历史数据）
        all_path = cls._shipping_all_path()
        try:
            existing = {}
            if os.path.exists(all_path):
                with open(all_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing.update(data)
            with open(all_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=4)
            logger.info(f"成功更新全量合并 shipping 缓存")
        except Exception as e:
            logger.error(f"更新全量 shipping 缓存失败: {e}")


class OrdersManager:
    """
    管理订单输出文件。
    每天独立一个文件：output/orders_YYYY-MM-DD.json
    """

    @staticmethod
    def _orders_path(date_str: str = None) -> str:
        """返回指定日期的 orders 文件路径。date_str 格式 YYYY-MM-DD，默认今天。"""
        if not date_str:
            date_str = date.today().isoformat()
        return os.path.join("output", f"orders_{date_str}.json")

    @classmethod
    def load_orders(cls, date_str: str = None) -> list:
        """加载指定日期的 orders，返回列表。"""
        path = cls._orders_path(date_str)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 orders 失败 {path}: {e}")
            return []

    @classmethod
    def save_orders(cls, orders: list, date_str: str = None):
        """保存订单列表到指定日期的文件，自动创建目录。"""
        os.makedirs("output", exist_ok=True)
        path = cls._orders_path(date_str)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(orders, f, ensure_ascii=False, indent=4)
            logger.info(f"成功保存 {len(orders)} 条订单至 {path}")
        except Exception as e:
            logger.error(f"保存 orders 失败 {path}: {e}")

    @classmethod
    def merge_orders(cls, new_orders: list, date_str: str = None) -> list:
        """
        将新订单合并入已有的当日文件（按 order_no 去重，新的覆盖旧的）。
        返回合并后的完整列表。
        """
        existing = cls.load_orders(date_str)
        merged = {o["order_no"]: o for o in existing if o.get("order_no")}
        for o in new_orders:
            if o.get("order_no"):
                merged[o["order_no"]] = o
        result = list(merged.values())
        cls.save_orders(result, date_str)
        return result


class PendingOrdersManager:
    """
    管理所有待写入多维表的订单暂存区。
    格式：{ order_no: { ...order_fields..., sync_status, synced_at } }
    持久化至 output/cache/pending_orders.json。

    sync_status 取值：
        pending  — 尚未写入多维表
        synced   — 已成功写入多维表
        anomaly  — 业务日期早于今天，异常跳过
    """
    CACHE_FILE = os.path.join(CACHE_DIR, "pending_orders.json")

    @classmethod
    def load_pending(cls) -> dict:
        """加载暂存区，返回 { order_no: order_dict }。"""
        if not os.path.exists(cls.CACHE_FILE):
            return {}
        try:
            with open(cls.CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 pending_orders 失败: {e}")
            return {}

    @classmethod
    def save_pending(cls, data: dict):
        """保存暂存区。"""
        os.makedirs(CACHE_DIR, exist_ok=True)
        try:
            with open(cls.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.debug(f"pending_orders 已保存，共 {len(data)} 条")
        except Exception as e:
            logger.error(f"保存 pending_orders 失败: {e}")

    @classmethod
    def add_orders(cls, orders: list):
        """
        将新解析的订单合并入暂存区。
        - 若 order_no 不存在：新增，状态 pending
        - 若已存在且状态为 synced，但内容有变化：重置为 pending（内容更新）
        - 若已存在且状态为 pending：直接覆盖
        - 若已存在且状态为 anomaly：保持 anomaly 不变
        """
        pending = cls.load_pending()
        changed = 0

        for order in orders:
            order_no = order.get("order_no", "").strip()
            if not order_no:
                continue

            existing = pending.get(order_no)
            new_entry = dict(order)

            if existing is None:
                # 全新订单
                new_entry["sync_status"] = "pending"
                new_entry["synced_at"] = None
                pending[order_no] = new_entry
                changed += 1
            elif existing.get("sync_status") == "anomaly":
                # 异常订单保持不变
                pass
            elif existing.get("sync_status") == "synced":
                # 检查内容是否有变化（比较除状态字段外的核心字段）
                _IGNORE = {"sync_status", "synced_at"}
                old_core = {k: v for k, v in existing.items() if k not in _IGNORE}
                new_core = {k: v for k, v in new_entry.items() if k not in _IGNORE}
                if old_core != new_core:
                    new_entry["sync_status"] = "pending"
                    new_entry["synced_at"] = None
                    pending[order_no] = new_entry
                    changed += 1
                    logger.info(f"[{order_no}] 内容有变化，重置为 pending")
            else:
                # pending 状态：直接覆盖
                new_entry["sync_status"] = "pending"
                new_entry["synced_at"] = None
                pending[order_no] = new_entry
                changed += 1

        if changed > 0:
            cls.save_pending(pending)
            logger.info(f"pending_orders 更新了 {changed} 条订单")

    @classmethod
    def mark_synced(cls, order_nos: list, synced_at: str = None):
        """批量将订单标记为已写入。"""
        if not order_nos:
            return
        pending = cls.load_pending()
        now = synced_at or datetime.now().isoformat()
        for order_no in order_nos:
            if order_no in pending:
                pending[order_no]["sync_status"] = "synced"
                pending[order_no]["synced_at"] = now
        cls.save_pending(pending)
        logger.info(f"已标记 {len(order_nos)} 条订单为 synced")

    @classmethod
    def mark_anomaly(cls, order_nos: list):
        """批量将订单标记为异常。"""
        if not order_nos:
            return
        pending = cls.load_pending()
        for order_no in order_nos:
            if order_no in pending:
                pending[order_no]["sync_status"] = "anomaly"
        cls.save_pending(pending)
        logger.warning(f"已标记 {len(order_nos)} 条异常订单: {order_nos}")

    @classmethod
    def get_by_status(cls, status: str) -> list:
        """按 sync_status 筛选，返回 list。"""
        pending = cls.load_pending()
        return [o for o in pending.values() if o.get("sync_status") == status]
