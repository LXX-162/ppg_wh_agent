import logging
import copy
from .normalizers.requirement_normalizer import RequirementNormalizer
from .normalizers.contact_normalizer import ContactNormalizer
from .normalizers.address_normalizer import AddressNormalizer
from .normalizers.logistics_normalizer import LogisticsNormalizer

logger = logging.getLogger(__name__)

class FieldNormalizer:
    """
    业务修正层（Normalizer）总控流水线
    原则：
    1. Parser 永远忠于原文。
    2. Normalizer 负责基于业务规则对提取的不规范数据进行二次修正。
    3. 每条规则依据领域拆分在 business/normalizers/ 下。
    """

    @classmethod
    def normalize(cls, order_dict: dict) -> dict:
        """
        执行规范化的总入口
        :param order_dict: Parser 提取输出的原始 dict
        :return: 经过业务规则清洗修正后的新 dict
        """
        # 深拷贝以确保不修改输入对象
        order = copy.deepcopy(order_dict)
        
        # 日期等基础信息清洗
        from .normalizers.order_info_normalizer import OrderInfoNormalizer
        order = OrderInfoNormalizer.normalize_date(order)
        
        # 依次经过流水线上的各种清洗规则
        order = RequirementNormalizer.normalize(order)
        order = ContactNormalizer.normalize(order)
        
        # 地址与收货单位相关
        order["raw_address"] = order.get("address", "")
        order = AddressNormalizer.normalize_address(order)
        order = AddressNormalizer.normalize_receiver(order)
        order = AddressNormalizer.normalize_city(order)
        
        # 物流与危管
        order = LogisticsNormalizer.normalize_shipping(order)
        order = LogisticsNormalizer.normalize_danger(order)
        
        # 移除内部临时辅助字段，防止输出到 JSON
        order.pop("raw_address", None)
        
        return order
