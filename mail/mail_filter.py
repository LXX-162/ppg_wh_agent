class MailFilter:
    # 白名单配置：发件人名称关键词列表
    PDF_ORDER_CONTACTS = [
        "juan wen",
        # 后续新增PDF订单发件人加在这里
    ]
    
    SHIPPING_INFO_CONTACTS = [
        "xu jiayi",
        "he jinlan",  # 兼容 He, Jinlan / JHe@ppg.com 等形式
        # 后续新增物流信息发件人加在这里
    ]
    
    @staticmethod
    def _match_contact(sender_lower: str, contact: str) -> bool:
        """
        检查发件人是否匹配某个联系人
        兼容: "juan wen" 匹配 "Wen, Juan" / "JuanWen" / "juan.wen@xxx"
        """
        # 将联系人的名和姓拆开
        parts = contact.split()
        # 所有部分都要在发件人字符串中出现
        return all(part in sender_lower for part in parts)
    
    @staticmethod
    def get_type(mail):
        """
        根据发件人分类邮件类型
        
        :param mail: 邮件数据字典，需包含 'sender' 字段
        :return: 返回分类字符串：PDF_ORDER, SHIPPING_INFO 或 UNKNOWN
        """
        if not mail or not isinstance(mail, dict):
            return "UNKNOWN"
            
        sender = mail.get("sender", "").lower()
        
        # 白名单匹配 - PDF订单
        for contact in MailFilter.PDF_ORDER_CONTACTS:
            if MailFilter._match_contact(sender, contact):
                return "PDF_ORDER"
        
        # 白名单匹配 - 物流信息
        for contact in MailFilter.SHIPPING_INFO_CONTACTS:
            if MailFilter._match_contact(sender, contact):
                return "SHIPPING_INFO"
        
        return "UNKNOWN"