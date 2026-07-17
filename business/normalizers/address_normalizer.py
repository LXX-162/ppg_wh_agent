import re

class AddressNormalizer:
    """业务修正规则：地址与相关实体（收货单位、省市区）"""
    
    @classmethod
    def normalize_address(cls, order: dict) -> dict:
        """
        规则：
        1. 优先从客户要求中提取地址
        2. 如果没有，则清理原始 address 字符串中的杂音（如订单号、电话、英文抬头等）
        3. 从清理后的字符串中精准提取中文地址部分
        """
        requirement = order.get("requirement", "")
        address = order.get("address", "")
        
        # 提取标准中文地址的精准正则：必须以 省/市/区 开启，并使用贪婪匹配到最后一个结尾词
        addr_pattern = r'([\u4e00-\u9fa5]{2,8}(?:省|市|区|自治区|自治州)[\u4e00-\u9fa5A-Za-z0-9_ \-（）\(\)]+(?:号|公司|集团|厂|仓库|基地|中心|车间|工业园|园区|区)[）\)]?)'
        
        # 1. 优先从客户要求中提取地址
        if requirement:
            req_match = re.search(addr_pattern, requirement)
            if req_match:
                order["address"] = req_match.group(1).replace('\n', ' ').strip()
                # 剔除中文字符间的空格
                order["address"] = re.sub(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])', '', order["address"])
                return order
                
        # 2. 清理原始 address 字符串
        # 剔除各种杂音
        address = re.sub(r'实际发货[:：].*?(?=\n|$)', ' ', address, flags=re.IGNORECASE)
        address = re.sub(r'PPG\s*涂料（[^）]+）有限公司|庞贝捷涂料（[^）]+）有限公司', ' ', address)
        address = re.sub(r'Frt bill.*?(?=\n|$)', ' ', address, flags=re.IGNORECASE)
        # 剔除带有 "电话:" 的
        address = re.sub(r'电话[:：]?[A-Za-z0-9-\s]+', ' ', address)
        # 剔除游离的 86-xxxx 电话
        address = re.sub(r'(?<!\d)86\s*-?\s*\d{2,3}\s*-?\s*\d{4}\s*-?\s*\d{4}', ' ', address)
        # 剔除订单号和 Waybill
        address = re.sub(r'订单号[:：]?\s*[A-Za-z0-9_-]+', ' ', address)
        address = re.sub(r'Waybill[:：]?\s*[A-Za-z0-9_-]*', ' ', address)
        
        # 把多个连续换行和空格统一为单个空格
        address = re.sub(r'[\r\n]+', ' ', address)
        address = re.sub(r'[ \t]+', ' ', address).strip()
        
        # 如果有 ~ 分隔，前面通常是英文公司名，去掉
        if '~' in address:
            address = address.split('~')[-1]
            
        # 3. 再用精准正则尝试去框出最核心的中文地址
        if address:
            addr_match = re.search(addr_pattern, address)
            if addr_match:
                final_addr = addr_match.group(1).replace('\n', ' ').strip()
                final_addr = re.sub(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])', '', final_addr)
                order["address"] = final_addr
                return order
                
            # 兜底：如果没匹配上（比如没有 省/市），就直接用清理过后的原句
            final_addr = re.sub(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])', '', address)
            order["address"] = final_addr
            
        return order

    _cached_receiver_list = None
    
    @classmethod
    def get_receiver_list(cls):
        """懒加载从飞书多维表格获取收货单位列表并进行内存缓存"""
        if cls._cached_receiver_list is not None:
            return cls._cached_receiver_list
            
        from utils.config import load_config
        from feishu.bitable import BitableClient
        import logging
        
        logger = logging.getLogger(__name__)
        config = load_config()
        
        app_id = config.get("FEISHU_APP_ID")
        app_secret = config.get("FEISHU_APP_SECRET")
        app_token = config.get("FEISHU_BITABLE_APP_TOKEN")
        table_id = config.get("FEISHU_RECEIVER_TABLE_ID")
        
        if not all([app_id, app_secret, app_token, table_id]):
            logger.error("Missing Feishu Bitable configuration for receivers. Using empty list.")
            cls._cached_receiver_list = []
            return cls._cached_receiver_list
            
        try:
            client = BitableClient(app_id, app_secret)
            records = client.get_records(app_token, table_id)
            receivers = []
            for record in records:
                fields = record.get("fields", {})
                # 获取“收货单位简称”列的值
                name = fields.get("收货单位简称")
                if name:
                    # 有些时候可能返回列表形式（如多选字段或文本），确保转为字符串
                    if isinstance(name, list) and len(name) > 0:
                        name = name[0]
                    if isinstance(name, dict) and "text" in name:
                        name = name["text"]
                        
                    name_str = str(name).strip()
                    if name_str:
                        receivers.append(name_str)
            
            logger.info(f"成功从飞书多维表格加载了 {len(receivers)} 个收货单位。")
            cls._cached_receiver_list = receivers
        except Exception as e:
            logger.error(f"Failed to load receivers from Feishu: {e}")
            cls._cached_receiver_list = []
            
        return cls._cached_receiver_list

    @classmethod
    def normalize_receiver(cls, order: dict) -> dict:
        """业务修正规则：收货单位匹配"""
        # 动态获取收货单位列表 (带缓存)
        receiver_list = cls.get_receiver_list()
        
        raw_address = order.get("address", "")
        requirement = order.get("requirement", "")
        text_pool = f"{raw_address} {requirement}"
        
        def can_partition(s, text):
            n = len(s)
            dp = [False] * (n + 1)
            dp[0] = True
            for i in range(1, n + 1):
                for j in range(i):
                    if dp[j]:
                        chunk = s[j:i]
                        # 允许的最小 chunk 长度为 2，以防止单个字（如“厂”、“库”）造成的过度匹配
                        if len(chunk) >= 2 and chunk in text:
                            dp[i] = True
                            break
            return dp[n]
            
        matched_receivers = []
        for receiver in receiver_list:
            # 如果收货单位名称少于2个字，直接全字匹配
            if len(receiver) < 2:
                if receiver in text_pool:
                    matched_receivers.append(receiver)
            else:
                if can_partition(receiver, text_pool):
                    matched_receivers.append(receiver)
                
        if matched_receivers:
            # 优先选择匹配到的名字最长的（越长越精确）
            best_match = max(matched_receivers, key=len)
            order["receiver"] = best_match
        else:
            order["receiver"] = ""
            
        return order

    @classmethod
    def normalize_city(cls, order: dict) -> dict:
        """业务修正规则：城市提取"""
        # TODO: 从地址中正则提取出省/市
        return order
