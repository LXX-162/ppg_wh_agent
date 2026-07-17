class LogisticsNormalizer:
    """业务修正规则：发运与危险品"""

    @classmethod
    def normalize_shipping(cls, order: dict) -> dict:
        """业务修正规则：发运方式结合"""
        # TODO: 处理发运方式，可能结合外部缓存的数据
        return order

    @classmethod
    def normalize_danger(cls, order: dict) -> dict:
        """业务修正规则：危险品类别"""
        # TODO: 处理危险品类别，可能结合外部缓存的数据
        return order
