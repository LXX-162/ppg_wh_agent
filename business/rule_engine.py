import logging
from parser.schema import OrderData

logger = logging.getLogger(__name__)

class RuleEngine:
    def __init__(self):
        pass

    def apply_rules(self, parsed_dict: dict) -> dict:
        """
        应用业务规则：如清洗字段格式、补充默认值等。
        """
        logger.info("Applying business rules to parsed data...")
        
        # 填充默认值
        if not parsed_dict.get("订单状态"):
            parsed_dict["订单状态"] = "正常"
        if not parsed_dict.get("发运方式"):
            parsed_dict["发运方式"] = "零担"
        if not parsed_dict.get("产品特性"):
            parsed_dict["产品特性"] = "DG"
            
        try:
            # 校验数据格式和必填项
            validated_data = OrderData(**parsed_dict)
            return validated_data.model_dump()
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            # 根据实际需要，可以选择抛出异常或返回原始字典
            return parsed_dict
