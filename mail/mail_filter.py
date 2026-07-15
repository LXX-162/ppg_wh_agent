class MailFilter:
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
        
        # 匹配 Juan Wen (兼容 Wen, Juan 或 JuanWen 等形式)
        if "juan" in sender and "wen" in sender:
            return "PDF_ORDER"
            
        # 匹配 Xu Jiayi (兼容 Xu, Jiayi 或 JiayiXu 等形式)
        if "xu" in sender and "jiayi" in sender:
            return "SHIPPING_INFO"
            
        # 其他情况
        return "UNKNOWN"
