import logging
from utils.cache_manager import CacheManager

logger = logging.getLogger(__name__)

class LogisticsNormalizer:
    """业务修正规则：发运与危险品"""

    _shipping_cache = None

    @classmethod
    def _get_cache(cls):
        """懒加载获取缓存字典"""
        if cls._shipping_cache is None:
            cls._shipping_cache = CacheManager.load_cache()
        return cls._shipping_cache

    @classmethod
    def normalize_shipping(cls, order: dict) -> dict:
        """业务修正规则：发运方式（仅缓存有值时覆盖，PDF 解析结果优先）"""
        order_no = order.get("order_no", "").strip()
        shipping_info = cls._get_cache().get(order_no, {})
        cached_shipping = shipping_info.get("shipping", "")
        if cached_shipping:
            order["发运方式"] = cached_shipping
        return order

    @classmethod
    def normalize_danger(cls, order: dict) -> dict:
        """业务修正规则：危险品类别（仅缓存有值时覆盖，PDF 解析结果优先）"""
        order_no = order.get("order_no", "").strip()
        shipping_info = cls._get_cache().get(order_no, {})
        cached_danger = shipping_info.get("danger", "")
        if cached_danger:
            order["危险品类别"] = cached_danger
        # PDF 原文解析结果优先级最高（如果存在），覆盖缓存中的值
        pdf_danger = order.get("pdf_danger", "")
        if pdf_danger:
            order["危险品类别"] = pdf_danger
        return order
