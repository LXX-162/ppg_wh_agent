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
        """业务修正规则：发运方式结合"""
        order_no = order.get("order_no", "").strip()
        shipping_info = cls._get_cache().get(order_no, {})
        order["发运方式"] = shipping_info.get("shipping", "")
        return order

    @classmethod
    def normalize_danger(cls, order: dict) -> dict:
        """业务修正规则：危险品类别"""
        order_no = order.get("order_no", "").strip()
        shipping_info = cls._get_cache().get(order_no, {})
        order["危险品类别"] = shipping_info.get("danger", "")
        return order
