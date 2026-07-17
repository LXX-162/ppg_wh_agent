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
            if re.match(r'^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})$', lines[i]):
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
        
        # 将 data 分割成 blocks
        blocks = []
        current_block = []
        date_pattern = re.compile(r'^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})$')
        
        for i in range(data_start, len(lines)):
            line = lines[i]
            if not line:
                continue
            if date_pattern.match(line):
                if current_block:
                    blocks.append(current_block)
                current_block = [line]
            else:
                if current_block:
                    current_block.append(line)
                    
        if current_block:
            blocks.append(current_block)
            
        for block in blocks:
            if len(block) > delivery_idx:
                delivery_no = block[delivery_idx]
                
                danger = ""
                # 如果这个块中存在单独一行的 DG 或 NDG
                for item in block:
                    item_upper = item.upper()
                    if item_upper in ["DG", "NDG"]:
                        danger = item_upper
                        break
                
                result[delivery_no] = {
                    "shipping": shipping,
                    "danger": danger
                }
                
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
        # 1. 优先通过正文的“发货单号:”来识别，过滤掉中间可能的乱码（比如二维码）
        match = re.search(r'发货单号\s*[:：]([\s\S]{0,100})', text)
        if match:
            chunk = match.group(1)
            # 策略A: 连续的11开头的长数字 (处理跨行但数字连续的情况，例如换行后的 11965813)
            m2 = re.search(r'(11\d{6,})', chunk)
            if m2:
                result = m2.group(1)
                logger.info(f"提取 [单号] (来自文本发货单号-连续) -> 成功: True | 内容: {result}")
                return result
                
            # 策略B: 数字被乱码打断的情况，比如 Í11+9Ä6\6r0Ã82Î -> 11966082
            first_line = chunk.split('\n')[0]
            digits_only = re.sub(r'\D', '', first_line)
            if digits_only.startswith('11') and len(digits_only) >= 8:
                logger.info(f"提取 [单号] (来自文本发货单号-乱码过滤) -> 成功: True | 内容: {digits_only}")
                return digits_only
            
        # 2. 次选兜底逻辑：订单号
        match = re.search(r'订单号[:：]\s*([A-Za-z0-9_-]+)', text)
        if match:
            result = match.group(1)
            logger.info(f"提取 [单号] (来自文本订单号) -> 成功: True | 内容: {result}")
            return result
            
        # 3. 再次选逻辑：文本里孤立的 11 开头的数字
        match = re.search(r'(11\d{6,})', text)
        if match:
            result = match.group(1)
            logger.info(f"提取 [单号] (来自孤立数字) -> 成功: True | 内容: {result}")
            return result
            
        # 4. 最后才从文件名提取（因为用户反映有时候文件名命名会和里面不一致，因此优先级降到最低）
        if filename:
            match = re.search(r'(11\d{6,})', filename)
            if match:
                result = match.group(1)
                logger.info(f"提取 [单号] (来自文件名) -> 成功: True | 内容: {result}")
                return result
                
        logger.info(f"提取 [单号] -> 成功: False | 内容: ")
        return ""

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
        if not result:
            # 使用更宽泛的正则去寻找 scrambled 的联系人行，例如 "客P户G联联系系人人"
            match = re.search(r'客.*?户.*?联.*?系.*?人.*?(?:[:：\?？]+)(.*?)(?:PPG|运输|承运|发货单号|电话|\n|$)', text, re.IGNORECASE)
            if match:
                result = match.group(1).strip()
        logger.info(f"提取 [联系人] -> 成功: {bool(result)} | 内容: {result}")
        return result

    @staticmethod
    def extract_address(text: str) -> str:
        # 首选明确的标签，加上冒号防止匹配到页底的"公司地址"
        result = ContentParser.extract_block(text, ["收货地址:", "收货地址：", "交货至:", "交货至："], ["订单号", "电话", "传真", "客户联系人", "Waybill"])
        if not result:
            # 备用抽取逻辑：从客户向下找，直到运输公司或发货单号或客户联系人
            result_fallback = ContentParser.extract_block(text, ["客户:", "客户："], ["运输公司", "Carrier", "发货单号", "客户联系人"])
            if result_fallback:
                lines = [line.strip() for line in result_fallback.splitlines() if line.strip()]
                
                # 寻找起步界限 (Frt bill 或 电话 或 SBU)
                start_idx = 0
                for i, line in enumerate(lines):
                    if "Frt bill" in line or "SBU:" in line or "电话" in line:
                        start_idx = i
                        break
                        
                # 收集起步界限之后直到倒数第二行的所有行 (倒数第一行通常是 城市, 省份, 邮编)
                if len(lines) > 1:
                    address_lines = lines[start_idx:-1]
                    result = " ".join(address_lines)
                else:
                    result = result_fallback
                    
                # 进一步清理带入的噪声
                result = re.sub(r'(?:电话|传真|Frt bill|SBU)[:：]\s*[\d\-\sA-Za-z]+', ' ', result)
                result = re.sub(r'Waybill:?', ' ', result, flags=re.IGNORECASE)
                result = re.sub(r'订单号[:：]\s*[A-Za-z0-9]+', ' ', result)
                result = re.sub(r'月结库|月结仓', ' ', result)

                result = re.sub(r'\s+', ' ', result).strip()
                
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
