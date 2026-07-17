import logging
import re

logger = logging.getLogger(__name__)

class ContactNormalizer:
    """业务修正规则：联系人"""
    
    @classmethod
    def normalize(cls, order: dict) -> dict:
        """
        规则：将客户要求里出现的联系人，以及原本提取出的客户联系人都写入（如有），
        并把客户要求里提取的写在前面，同时做基础去重。
        """
        contact = order.get("contact", "").strip()
        requirement = order.get("requirement", "")

        # 1. 尝试从客户要求中提取
        req_contact = ""
        if requirement:
            req_contact = cls._extract_contact_from_text(requirement)

        # 2. 从原 contact 字段提取并清理
        base_contact = ""
        if contact:
            # 清理杂音
            contact = re.sub(r'[\s\n]*操作人[:：\s]*[A-Za-z0-9_]+', '', contact)
            contact = re.sub(r'[\s\n]*Carrier.*', '', contact)
            
            # 使用提取器进行精准提纯
            extracted = cls._extract_contact_from_text(contact)
            if extracted:
                base_contact = extracted
            else:
                # 兜底：如果没提取到电话号码，至少去掉常见的乱码字符 (保留中文、英文、数字和常见标点)
                cleaned = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9\s/,\-:]', '', contact)
                base_contact = cleaned.replace('\n', ' ').strip()

        # 3. 组合两者
        final_contacts = []
        if req_contact:
            final_contacts.append(req_contact)
            logger.info(f"[Rule: Contact] 成功从 requirement 提取联系人 -> {req_contact}")

        if base_contact:
            # 如果 req_contact 中完全没有 base_contact 的信息，才附加，避免重复
            if base_contact not in req_contact:
                final_contacts.append(base_contact)

        order["contact"] = " ".join(final_contacts).strip()
        return order

    @classmethod
    def _extract_contact_from_text(cls, text: str) -> str:
        # 手机或固话的单体正则
        phone_pattern = r'1[3-9]\d{9}|0\d{2,3}-?\d{7,8}(?:-\d{1,4})?'
        # 允许多个电话通过空格、斜杠或逗号连接
        multi_phone_pattern = rf'(?:{phone_pattern})(?:(?:\s*[/,，]\s*|\s+)(?:{phone_pattern}))*'
        
        contacts = []
        working_text = text
        
        # 策略 1: 带有明确动词或前缀的名字+电话 (非常精准)
        p_exact = re.compile(rf'(?:通知|交给|联系|找|签收人(?:是)?|收货人(?:是)?|联系人(?:是)?|采购(?:是)?)[\s:]*([\u4e00-\u9fa5]{{2,4}}(?:/[A-Za-z\u4e00-\u9fa5]+)?)[:：\-\s]*({multi_phone_pattern})')
        for match in p_exact.finditer(working_text):
            name = match.group(1).strip()
            phone = match.group(2).strip()
            contacts.append(f"{name} {phone}")
            working_text = working_text.replace(match.group(0), " " * len(match.group(0)))
            
        # 策略 2: 名字直接跟着电话号码的启发式 (名字2-4个中文字符，后面跟着电话)
        p_heuristic = re.compile(rf'([^\u4e00-\u9fa50-9]|^)([\u4e00-\u9fa5]{{2,4}}(?:/[A-Za-z\u4e00-\u9fa5]+)?)\s*[:：\-]?\s*({multi_phone_pattern})')
        for match in p_heuristic.finditer(working_text):
            name = match.group(2).strip()
            phone = match.group(3).strip()
            if not any(w in name for w in ["公司", "需要", "批次", "发货", "备注", "要求", "电话", "手机", "送达", "地址", "限公司", "到达", "拨打", "送到", "前台"]):
                contacts.append(f"{name} {phone}")
                working_text = working_text.replace(match.group(0), " " * len(match.group(0)))
            
        # 策略 3: 如果还是没有任何名字，退回到仅仅提取电话号码
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
                
        return " ".join(result)
