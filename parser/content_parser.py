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
    def extract_company_name(text: str) -> str:
        """
        从 PDF 文本中提取客户公司名。
        位置：在"客户"字段的 ~ 之后。

        已知结构模式：
          A) 公司名完整在 ~ 到 Frt bill 之间（主流情况）
          B) 公司名被 Frt bill 截断，后半段藏在 "电话：...  订单号:" 行中
          C) ~ 后出现两家公司（如 东莞市浚哲 和 宁波四维尔），取最后一家
          D) ~ 后直接是 PPG 自家公司（兜底，原样返回）

        全局策略：
          1. 扩展搜索范围到"电话："行，从中抢救被截断的公司名后半段
          2. 去除 PPG 噪声行；混合行保留非 PPG 部分
          3. 当有多个候选段时取最后一段（最靠近地址的那个）
          4. 若仍无结果，回退取原始 PPG 公司名
        """
        idx = text.find('~')
        if idx == -1:
            return ""

        _PPG_CORE = re.compile(r'庞贝捷涂料|PPG\s*涂料|PPG\s+Coatings?', re.IGNORECASE)
        _DATE_NOISE = re.compile(
            r'(实际|计划)发货|July|August|January|February|March|April|May|June|'
            r'September|October|November|December', re.IGNORECASE
        )
        # 地址起始：2~8个汉字后跟省市关键词
        _ADDR_START = re.compile(
            r'[\u4e00-\u9fa5]{2,8}(?:省|市|自治区|自治州|开发区|新区|高新区|实验区|县)'
        )

        # ── 第一段：~ 到 Frt bill ────────────────────────────────────
        chunk_pre = text[idx + 1:]
        frt_pos = chunk_pre.find('Frt bill')
        if frt_pos != -1:
            chunk_pre = chunk_pre[:frt_pos]

        # ── 第二段：Frt bill 后的"电话："行（抢救截断的公司名后半段） ──
        # 结构："电话：...  [公司名后半段]  订单号: XXXX"
        rescued_suffix = ""
        frt_abs = text.find('Frt bill', idx)
        if frt_abs != -1:
            tel_pos = text.find('电话：', frt_abs)
            if tel_pos != -1:
                tel_line_end = text.find('\n', tel_pos)
                tel_line = text[tel_pos: tel_line_end if tel_line_end != -1 else tel_pos + 200]
                # 去掉"电话：86..."部分，留下中间的中文内容
                tel_line = re.sub(r'电话：[\d\s\-]+', '', tel_line)
                # 去掉"订单号: XXXX"及之后
                tel_line = re.sub(r'订单号\s*[:：]\s*\S+.*', '', tel_line).strip()
                # 如果剩余内容不是地址，可能是公司名后半段
                if tel_line and not _ADDR_START.search(tel_line[:6]):
                    rescued_suffix = tel_line.strip()

        # ── 处理 ~ 到 Frt bill 之间的行 ─────────────────────────────
        lines = [ln.strip() for ln in chunk_pre.splitlines()]
        fragments = []  # 每个元素代表一个独立的公司名候选片段

        for ln in lines:
            if not ln:
                continue
            # 去掉日期噪声
            date_m = _DATE_NOISE.search(ln)
            if date_m:
                ln = ln[:date_m.start()].strip()
            if not ln:
                continue

            if _PPG_CORE.search(ln):
                # 混合行：去掉 PPG 部分，保留剩余
                clean = _PPG_CORE.sub('', ln)
                clean = re.sub(r'（[^）]{1,6}）有限公司', '', clean)
                clean = re.sub(r'（[^）]{1,6}）', '', clean)
                clean = re.sub(r'^有限公司\s*', '', clean).strip()
                if len(clean.replace(' ', '')) >= 3:
                    fragments.append(clean)
                # 纯 PPG 行或清理后太短：丢弃，作为分隔符（代表一个新候选的开始）
                else:
                    # 用 None 作为分隔标记
                    fragments.append(None)
                continue

            # 截断到地址起始处
            addr_m = _ADDR_START.search(ln)
            if addr_m:
                ln = ln[:addr_m.start()].strip()
            if ln:
                fragments.append(ln)

        # ── 拼接：按 rescued_suffix 的完整性决定策略 ────────────────

        # 将 fragments 按 None 分割成独立候选段（None 是不同公司间的分隔符）
        segments = []
        current = []
        for f in fragments:
            if f is None:
                if current:
                    segments.append("".join(current))
                current = []
            else:
                current.append(f)
        if current:
            segments.append("".join(current))

        _COMPLETE_MARKERS = re.compile(r'有限公司|股份公司|月结库|集团有限|仓储有限')

        # rescued_suffix 是一个完整公司名（Case B：多家公司，取最后一家）
        rescued_is_complete = (
            bool(rescued_suffix)
            and len(rescued_suffix) >= 8
            and _COMPLETE_MARKERS.search(rescued_suffix)
        )

        if rescued_is_complete:
            # 电话行抢救出的是完整的客户公司名，直接使用
            company_name = rescued_suffix

        elif rescued_suffix:
            # rescued_suffix 是短尾巴（如"限公司月结库"），需要拼到前段末尾
            last_seg = segments[-1].strip() if segments else ""
            company_name = last_seg + rescued_suffix

        else:
            # 没有 rescued_suffix：PPG 行只是噪声，把所有片段拼起来
            # (处理公司名被 PPG 行打断跨行的情况)
            company_name = "".join(f for f in fragments if f is not None)

        # ── 截断到地址起始处 ──────────────────────────────────────
        addr_m = _ADDR_START.search(company_name)
        if addr_m:
            company_name = company_name[:addr_m.start()].strip()

        # ── 兜底：若仍为空，取 ~ 后原始第一行（PPG 自家公司名）────────
        if not company_name:
            for ln in lines:
                if not ln:
                    continue
                date_m = _DATE_NOISE.search(ln)
                if date_m:
                    ln = ln[:date_m.start()].strip()
                if ln:
                    addr_m = _ADDR_START.search(ln)
                    if addr_m:
                        ln = ln[:addr_m.start()].strip()
                    if ln:
                        logger.info(f"提取 [公司名] -> 成功(PPG兜底): {ln}")
                        return ln
            return ""

        logger.info(f"提取 [公司名] -> 成功: {bool(company_name)} | 内容: {company_name}")
        return company_name

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

                _CITY_LINE = re.compile(
                    r'[\u4e00-\u9fa5a-zA-Z\s]+,\s*[\u4e00-\u9fa5a-zA-Z\s]+,\s*\d{4,6},\s*CN'
                )

                # 找到 Frt bill/SBU 行作为地址区域的起始锚点
                frt_idx = -1
                for i, line in enumerate(lines):
                    if re.search(r'Frt bill|SBU:', line):
                        frt_idx = i
                        break

                # 地址区域：从 Frt bill 行开始（含）到末尾
                # （Frt bill 行及紧跟的电话/传真行可能包含嵌入的地址信息，
                #  通过后续正则清理去掉噪声文字而保留地址部分）
                addr_start = frt_idx if frt_idx != -1 else 0

                # 末尾截止：从末尾向前扫描，找到最后一个含城市行特征的行并排除其后内容
                # （有时城市行不是最后一行，如后面有乱码的承运商行）
                addr_end = len(lines)
                for _j in range(len(lines) - 1, addr_start - 1, -1):
                    if _CITY_LINE.search(lines[_j]):
                        addr_end = _j
                        break

                address_lines = lines[addr_start:addr_end]
                if address_lines:
                    result = " ".join(address_lines)
                elif len(lines) > 1:
                    result = " ".join(lines[:-1])
                else:
                    result = result_fallback

                # 正则清理：去掉噪声文字，但保留行内的地址内容
                # 1. 先整体清理 "Frt bill: SBU: XXXX" 整个复合串
                result = re.sub(r'Frt bill\s*[:：]\s*SBU\s*[:：]\s*[A-Za-z0-9]+', ' ', result)
                # 2. 再分别清理剩余的 SBU/电话/传真
                result = re.sub(r'(?:电话|传真|SBU)[:：]\s*[\d\-\sA-Za-z]+', ' ', result)
                result = re.sub(r'Waybill:?', ' ', result, flags=re.IGNORECASE)
                result = re.sub(r'订单号[:：]\s*[A-Za-z0-9]+', ' ', result)
                result = re.sub(r'月结库|月结仓', ' ', result)
                # 先压缩空格，再清理遗留的孤立冒号和公司名残片（确保 ^ 锚点能正确匹配）
                result = re.sub(r'\s+', ' ', result).strip()
                result = re.sub(r'^[:：]\s*', '', result)
                # 清理公司名残片（如独立的"有限公司"等出现在地址开头的噪声，前缀最多15汉字）
                result = re.sub(r'^[\u4e00-\u9fa5]{0,15}有限公司[\u4e00-\u9fa5]{0,4}\s*', '', result)

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
        company_name = ContentParser.extract_company_name(norm_text)
        
        logger.info("=== PDF 字段解析完成 ===")
        
        return {
            "order_no": order_no,
            "order_date": order_date,
            "address": address,
            "contact": contact,
            "requirement": requirement,
            "weight": weight,
            "quantity": quantity,
            "company_name": company_name,
        }

