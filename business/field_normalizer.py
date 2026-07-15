import logging
import copy

logger = logging.getLogger(__name__)

class FieldNormalizer:
    """
    业务修正层（Normalizer）
    原则：
    1. Parser 永远忠于原文。
    2. Normalizer 负责基于业务规则对提取的不规范数据进行二次修正。
    3. 每条规则均为独立的函数，互不影响。
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
        
        # 依次经过流水线上的各种清洗规则
        order = cls.normalize_contact(order)
        order = cls.normalize_address(order)
        order = cls.normalize_receiver(order)
        order = cls.normalize_city(order)
        order = cls.normalize_shipping(order)
        order = cls.normalize_danger(order)
        
        return order

    @classmethod
    def normalize_contact(cls, order: dict) -> dict:
        """
        业务修正规则：联系人
        【规则1】如果收货人字段已经有内容：保持原值，不要修改。
        【规则2】如果收货人为空，尝试从客户要求中恢复联系人。
        """
        contact = order.get("contact", "").strip()
        requirement = order.get("requirement", "")
        
        if contact:
            return order
            
        if not requirement:
            return order
            
        # 尝试从要求中提取
        extracted = cls._extract_contact_from_text(requirement)
        if extracted:
            order["contact"] = extracted
            logger.info(f"[Rule: Contact] 触发修正: 成功从 requirement 恢复联系人 -> {extracted}")
            
        return order

    @classmethod
    def _extract_contact_from_text(cls, text: str) -> str:
        import re
        
        # 手机或固话的单体正则
        phone_pattern = r'1[3-9]\d{9}|0\d{2,3}-?\d{7,8}(?:-\d{1,4})?'
        # 允许多个电话通过空格、斜杠或逗号连接
        multi_phone_pattern = rf'(?:{phone_pattern})(?:(?:\s*[/,，]\s*|\s+)(?:{phone_pattern}))*'
        
        contacts = []
        
        # 策略 1: 带有明确关键字前缀，可以紧跟电话，也可以有"电话"引导
        p1 = re.compile(rf'(?:联系人|收货人|收件人)[:：\s]*([\u4e00-\u9fa5a-zA-Z]{{2,10}})[\s,，]*(?:(?:电话|手机|联系电话)[:：\s]*)?({multi_phone_pattern})?')
        
        # 策略 2: 名字紧跟电话关键字
        p2 = re.compile(rf'([\u4e00-\u9fa5a-zA-Z]{{2,10}})[,，\s]*(?:电话|手机|联系电话)[:：\s]*({multi_phone_pattern})')
        
        # 策略 3: 名字直接跟着电话号码
        p3 = re.compile(rf'([\u4e00-\u9fa5]{{2,4}})[\s,，]+({multi_phone_pattern})')
        
        # 为了避免重复提取，提取完就把原文对应的部分抹掉 (用空格替换保证长度不变)
        working_text = text
        
        for match in p1.finditer(working_text):
            name = match.group(1).strip()
            phone = (match.group(2) or "").strip()
            contacts.append(f"{name} {phone}".strip())
            working_text = working_text.replace(match.group(0), " " * len(match.group(0)))
            
        for match in p2.finditer(working_text):
            name = match.group(1).strip()
            phone = match.group(2).strip()
            # 排除明显不是人名的词
            if not any(w in name for w in ["公司", "部门", "地址", "到达", "拨打", "送到"]):
                contacts.append(f"{name} {phone}".strip())
                working_text = working_text.replace(match.group(0), " " * len(match.group(0)))
            
        for match in p3.finditer(working_text):
            name = match.group(1).strip()
            phone = match.group(2).strip()
            if not any(w in name for w in ["公司", "需要", "批次", "发货", "备注", "要求", "电话", "手机", "送达", "地址", "限公司", "到达", "拨打", "送到", "前台"]):
                contacts.append(f"{name} {phone}".strip())
                working_text = working_text.replace(match.group(0), " " * len(match.group(0)))
            
        # 策略 4: 如果都没有找到名字，但有孤立的电话号码
        p_phone_only = re.compile(multi_phone_pattern)
        for match in p_phone_only.finditer(working_text):
            phone = match.group(0).strip()
            contacts.append(phone)
            working_text = working_text.replace(match.group(0), " " * len(match.group(0)))
            
        # 去重并组装
        result = []
        for c in contacts:
            if c not in result and c:
                result.append(c)
                
        return "；".join(result)

    @classmethod
    def normalize_address(cls, order: dict) -> dict:
        """业务修正规则：收货地址"""
        # TODO: 具体清洗逻辑，例如剥离混杂的发货日期或组织抬头
        return order

    @classmethod
    def normalize_receiver(cls, order: dict) -> dict:
        """业务修正规则：收货单位"""
        # TODO: 从收货地址或其他字段中拆分出收货单位
        return order

    @classmethod
    def normalize_city(cls, order: dict) -> dict:
        """业务修正规则：城市提取"""
        # TODO: 从地址中正则提取出省/市
        return order

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
