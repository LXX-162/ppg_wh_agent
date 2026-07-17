import re

class RequirementNormalizer:
    """业务修正规则：客户要求"""
    
    @classmethod
    def normalize(cls, order: dict) -> dict:
        """清理客户要求中的表格杂音和多余换行、空格"""
        requirement = order.get("requirement", "")
        if not requirement:
            return order
            
        # 剔除因为排版穿插进来的已知英文表头和其它表格字段
        noise_patterns = [
            r'Customer Receive',
            r'客户签收[：:]?',
            r'Cust Po[：:]?\s*[A-Za-z0-9_-]+',
            r'客户[：:]?\s*\d+',
            r'Org/Warehouse[：:]?\s*[A-Za-z0-9_/]+',
            r'操作人[：:]?\s*[A-Za-z0-9_]+',
            r'Approve'
        ]
        
        cleaned = requirement
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
            
        # 2. 把所有换行符替换为空格（然后再统一清理空格，或者直接干掉）
        cleaned = cleaned.replace('\n', ' ')
        cleaned = cleaned.replace('\r', ' ')
        
        # 3. 去掉中文字符之间多余的空格，如 "标 签" -> "标签"
        cleaned = re.sub(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])', '', cleaned)
            
        # 4. 把剩下多个连续空格统一为单个空格
        cleaned = re.sub(r'[ \t]+', ' ', cleaned).strip()
        
        if cleaned != requirement:
            order["requirement"] = cleaned
            
        return order
