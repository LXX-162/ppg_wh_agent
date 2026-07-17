from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class OrderInfoNormalizer:
    """业务修正规则：订单基础信息（如日期等）"""
    
    @classmethod
    def normalize_date(cls, order: dict) -> dict:
        """
        规则：将英文日期格式 "July 14, 2026" 转换为 "2026/7/14" 格式
        """
        date_str = order.get("order_date", "").strip()
        if not date_str:
            return order
            
        try:
            # 尝试解析 "Month DD, YYYY" 格式
            dt = datetime.strptime(date_str, "%B %d, %Y")
            formatted_date = f"{dt.year}/{dt.month}/{dt.day}"
            order["order_date"] = formatted_date
            logger.info(f"[Rule: Date] 成功转换日期: {date_str} -> {formatted_date}")
        except ValueError:
            # 可能是其他格式或者解析失败，原样返回
            logger.warning(f"[Rule: Date] 日期格式不匹配，跳过转换: {date_str}")
            
        return order
