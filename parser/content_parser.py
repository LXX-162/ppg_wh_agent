import logging
import re
import json

logger = logging.getLogger(__name__)

class ContentParser:
    def __init__(self):
        pass

    def extract_order_info(self, subject, body, pdf_text):
        """
        内容解析器，整合邮件主题、正文和 PDF 文本内容。
        """
        logger.info("Extracting order info from content...")
        
        combined_text = f"【主题】\n{subject}\n\n【正文】\n{body}\n\n【附件PDF】\n{pdf_text}"
        
        return {
            "raw_combined_text": combined_text,
        }

    @staticmethod
    def parse_shipping_mail(subject, text):
        """
        解析发货邮件
        1. 订单号使用 DELIVERY_NO 作为 Key
        2. 发运方式从邮件标题中获取
        3. 危险品类别查找 DG 或 NDG
        """
        lines = [line.strip() for line in text.splitlines()]
        
        try:
            header_start = lines.index("日期")
        except ValueError:
            return {}
            
        headers = []
        data_start = -1
        
        for i in range(header_start, len(lines)):
            if re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', lines[i]):
                data_start = i
                break
            headers.append(lines[i])
            
        if data_start == -1 or not headers:
            return {}
            
        shipping = ""
        # 预设的发运方式关键字（严格按照业务指定的四个选项）
        for kw in ["保温车", "包车", "零担", "自提"]:
            if kw in subject:
                shipping = kw
                break
                
        try:
            delivery_idx = headers.index("DELIVERY_NO")
        except ValueError:
            delivery_idx = 2
            
        result = {}
        record_len = len(headers)
        i = data_start
        
        while i < len(lines):
            chunk = lines[i : i + record_len]
            
            if not chunk or not re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', chunk[0]):
                break
                
            if len(chunk) > delivery_idx:
                delivery_no = chunk[delivery_idx]
                
                danger = ""
                for item in chunk:
                    item_upper = item.upper()
                    if item_upper in ["DG", "NDG"]:
                        danger = item_upper
                        break
                
                result[delivery_no] = {
                    "shipping": shipping,
                    "danger": danger
                }
                
            i += record_len
            
        return result

    # ================= PDF 解析重构区域 =================

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        标准化 PDF 文本
        - 去掉连续空格 (替换为单空格)
        - 统一换行
        - 去掉多余空行
        """
        if not text:
            return ""
        # 统一换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # 将多个连续空格替换为一个空格
        text = re.sub(r'[ \t]+', ' ', text)
        # 去掉多余空行
        text = re.sub(r'\n+', '\n', text)
        return text.strip()

    @staticmethod
    def extract_block(text: str, start_keywords: list, end_keywords: list) -> str:
        """
        找到开始字段和结束字段，返回中间所有内容。
        """
        start_pos = -1
        matched_start = ""
        for kw in start_keywords:
            pos = text.find(kw)
            if pos != -1 and (start_pos == -1 or pos < start_pos):
                start_pos = pos
                matched_start = kw
                
        if start_pos == -1:
            return ""
            
        # 截断前面的内容
        sub_text = text[start_pos + len(matched_start):]
        # 去掉紧跟的冒号、换行或空格
        sub_text = re.sub(r'^[:：\s]+', '', sub_text)
        
        # 找到最靠前的 end_keyword
        end_pos = -1
        for kw in end_keywords:
            pos = sub_text.find(kw)
            if pos != -1 and (end_pos == -1 or pos < end_pos):
                end_pos = pos
                
        if end_pos != -1:
            return sub_text[:end_pos].strip()
        else:
            return sub_text.strip()

    @staticmethod
    def extract_order_no(text: str, filename: str = "") -> str:
        # 优先从文件名提取 11 开头的数字
        if filename:
            match = re.search(r'(11\d{6,})', filename)
            if match:
                result = match.group(1)
                logger.info(f"提取 [单号] (来自文件名) -> 成功: True | 内容: {result}")
                return result
                
        # 其次从文本里寻找孤立的 11 开头的数字 (比如发货单号)
        match = re.search(r'(11\d{6,})', text)
        if match:
            result = match.group(1)
            logger.info(f"提取 [单号] (来自文本发货单号) -> 成功: True | 内容: {result}")
            return result
            
        # 兜底：原始的订单号逻辑
        match = re.search(r'订单号[:：]\s*([A-Za-z0-9_-]+)', text)
        result = match.group(1) if match else ""
        logger.info(f"提取 [单号] -> 成功: {bool(result)} | 内容: {result}")
        return result

    @staticmethod
    def extract_order_date(text: str) -> str:
        match = re.search(r'(计划发货|实际发货)[:：]\s*([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})', text)
        result = match.group(2) if match else ""
        logger.info(f"提取 [日期] -> 成功: {bool(result)} | 内容: {result}")
        return result
        
    @staticmethod
    def extract_weight(text: str) -> str:
        match = re.search(r'总毛重[:：\s]*([\d\.]+K?G?)', text, re.IGNORECASE)
        result = match.group(1) if match else ""
        logger.info(f"提取 [重量] -> 成功: {bool(result)} | 内容: {result}")
        return result

    @staticmethod
    def extract_quantity(text: str) -> str:
        matches = re.findall(r'Qty\s*\(数量\)[:：\s]*(\d+)', text)
        if not matches:
            matches = re.findall(r'数量[:：\s]*(\d+)', text)
            
        if matches:
            total = sum(int(m) for m in matches)
            logger.info(f"提取 [数量] -> 成功: True | 累加结果: {total}")
            return str(total)
        else:
            logger.info("提取 [数量] -> 成功: False | 内容: ")
            return ""

    @staticmethod
    def extract_contact(text: str) -> str:
        result = ContentParser.extract_block(text, ["客户联系人", "联系人"], ["PPG联系人", "运输公司", "承运商", "发货单号", "电话"])
        logger.info(f"提取 [联系人] -> 成功: {bool(result)} | 内容: {result}")
        return result

    @staticmethod
    def extract_address(text: str) -> str:
        result = ContentParser.extract_block(text, ["收货地址", "地址", "交货至"], ["订单号", "电话", "传真", "客户联系人", "Waybill"])
        if not result:
            # 备用抽取逻辑 (扩展抓取范围到 Waybill 或 运输公司)
            result_fallback = ContentParser.extract_block(text, ["客户:", "客户："], ["Waybill", "运输公司", "Carrier"])
            if result_fallback:
                result = result_fallback
        logger.info(f"提取 [地址] -> 成功: {bool(result)} | 内容: {result}")
        return result

    @staticmethod
    def extract_requirement(text: str) -> str:
        result = ContentParser.extract_block(
            text, 
            ["客户要求"], 
            ["UN No.", "UN None", "Description", "Item Ord.Qty", "Shipped Qty", "总毛重"]
        )
        logger.info(f"提取 [客户要求] -> 成功: {bool(result)} | 内容: {result}")
        return result

    @staticmethod
    def parse_pdf_text(raw_text: str, filename: str = "") -> dict:
        norm_text = ContentParser.normalize_text(raw_text)
        
        logger.info("=== 开始解析 PDF 字段 ===")
        
        order_no = ContentParser.extract_order_no(norm_text, filename)
        order_date = ContentParser.extract_order_date(norm_text)
        address = ContentParser.extract_address(norm_text)
        contact = ContentParser.extract_contact(norm_text)
        requirement = ContentParser.extract_requirement(norm_text)
        weight = ContentParser.extract_weight(norm_text)
        quantity = ContentParser.extract_quantity(norm_text)
        
        logger.info("=== PDF 字段解析完成 ===")
        
        return {
            "order_no": order_no,
            "order_date": order_date,
            "address": address,
            "contact": contact,
            "requirement": requirement,
            "weight": weight,
            "quantity": quantity
        }
