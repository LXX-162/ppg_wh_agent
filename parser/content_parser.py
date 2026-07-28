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
                # 策略1: 如果这个块中存在单独一行的 DG 或 NDG
                for item in block:
                    item_upper = item.upper()
                    if item_upper in ["DG", "NDG"]:
                        danger = item_upper
                        break
                
                # 策略2: 查找包含 "危险品" 表头的行，看同行或下一行是否有 DG/NDG
                if not danger:
                    for i, item in enumerate(block):
                        if "危险" in item:
                            # 检查当前行
                            dg_match = re.search(r'\b(DG|NDG)\b', item.upper())
                            if dg_match:
                                danger = dg_match.group(1)
                                break
                            # 检查下一行（如果存在）
                            if i + 1 < len(block):
                                dg_match2 = re.search(r'\b(DG|NDG)\b', block[i + 1].upper())
                                if dg_match2:
                                    danger = dg_match2.group(1)
                                    break
                
                # 策略3: 在块中查找独立出现的 DG/NDG 单词（非产品编码上下文）
                if not danger:
                    for item in block:
                        item_upper = item.upper()
                        # 匹配独立的 DG/NDG（前后是空格或行首/行尾）
                        dg_match = re.search(r'(?:^|\s)(DG|NDG)(?:\s|$)', item_upper)
                        if dg_match:
                            # 排除产品编码中的 DG 子串（如 BYPWB1DG02）
                            item_clean = re.sub(r'[A-Z0-9]{6,}', '', item_upper)
                            if re.search(r'(?:^|\s)(DG|NDG)(?:\s|$)', item_clean):
                                danger = dg_match.group(1)
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
        match = re.search(r'总毛重[:：\s]*([\d\.]+)', text, re.IGNORECASE)
        result = match.group(1) if match else ""
        if result:
            # 去掉小数部分尾部多余的 0（保留原始精度，如 1358.070 -> 1358.07, 1185.000 -> 1185）
            if '.' in result:
                
                result = result.rstrip('0').rstrip('.') if result.rstrip('0').rstrip('.') else '0'
        logger.info(f"提取 [重量] -> 成功: {bool(result)} | 内容: {result}")
        return result

    @staticmethod
    def extract_quantity(text: str) -> str:
        matches = re.findall(r'Qty\s*\(数量\)[:：\s]*([\d\.]+)', text)
        if not matches:
            matches = re.findall(r'数量[:：\s]*([\d\.]+)', text)
            
        if matches:
            total = sum(float(m) for m in matches)
            # 如果小数部分为 0，输出整数形式
            if total == int(total):
                logger.info(f"提取 [数量] -> 成功: True | 累加结果: {int(total)}")
                return str(int(total))
            else:
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
        # 地址起始：4~8个汉字后跟省市关键词（在公司名提取中仅用于 rescued_suffix 判断，
        # 最小4字避免误截如"昆山开发区"、"常州市"等公司名）
        _ADDR_START = re.compile(
            r'[\u4e00-\u9fa5]{4,8}(?:省|市|自治区|自治州|开发区|新区|高新区|实验区|县)'
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

            # 行内容为公司名片段，地址提取由 extract_address 负责，
            # 此处不截断，以免误将含"市/区/开发区"的公司名截断
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

        # ── 兜底：若仍为空，取 ~ 后原始第一行（PPG 自家公司名）────────
        if not company_name:
            for ln in lines:
                if not ln:
                    continue
                date_m = _DATE_NOISE.search(ln)
                if date_m:
                    ln = ln[:date_m.start()].strip()
                if ln:
                    logger.info(f"提取 [公司名] -> 成功(PPG兜底): {ln}")
                    return ln
            return ""

        logger.info(f"提取 [公司名] -> 成功: {bool(company_name)} | 内容: {company_name}")
        return company_name

    @staticmethod
    def extract_danger_from_pdf(text: str) -> str:
        """
        从 PDF 文本中提取危险品类别。
        匹配两种格式：

        格式A（逐行，旧版）：
            UN 1263
            3           <- 这个数字是 DG 类别
            PG III

        格式B（标准发货单，一行内）：
            UN 1263 Illusion Met. YF-SGM444M/17K-C1 ...
            3 P G III > CNT(桶) ...

        如果中间部分是 "NONE" / "None" -> NDG
        如果中间部分是数字（如 3, 4.1, 8 等）-> DG
        返回 "DG" 或 "NDG" 或 ""
        """
        # 格式A：严格逐行
        pattern_a = re.compile(
            r'UN\s+(?:\d+|None)\s*' '\n'
            r'(\d+(?:\.\d+)?|[Nn][Oo][Nn][Ee])\s*' '\n'
            r'PG\s+\w+',
            re.MULTILINE
        )
        match = pattern_a.search(text)
        if match:
            mid = match.group(1).strip().upper()
            if mid == "NONE":
                return "NDG"
            try:
                float(mid)
                return "DG"
            except ValueError:
                pass

        # 格式B：UN 数字 ... (中间跨行内容) ... 数字 P\s*G III/II/I
        pattern_b = re.compile(
            r'UN\s+(None|\d+)\b.*?'
            r'(None|\d+(?:\.\d+)?)\s+P\s*G\s+[IVXL]+',
            re.DOTALL | re.IGNORECASE
        )
        match_b = pattern_b.search(text)
        if match_b:
            cls_val = match_b.group(2).upper()
            if cls_val == "NONE":
                return "NDG"
            try:
                float(cls_val)
                return "DG"
            except ValueError:
                pass

        # 兜底1：检测 UN\s+None → PD 文本中标记为无危险品
        # 特征：UN None 数据行的下一行有 "PSN: PAINT - NOT REGULATED"
        # 注意：产品编码如 BYPWB1DG02 中的 DG 子串不应被误判为危险品
        un_none = re.search(r'UN\s+None\b', text, re.IGNORECASE)
        if un_none:
            after_un_none = text[un_none.end():un_none.end() + 200]
            # PSN: PAINT - NOT REGULATED → 明确的无危险品标记
            if 'NOT REGULATED' in after_un_none.upper():
                return "NDG"
            # 即使 PSN 中没出现 NOT REGULATED，UN None 本身也代表无危险品
            return "NDG"

        # 兜底2：如果有数据行中有明显的 DG 危险品类别
        # 在 UN 数字 后面，找 数字(类别) + P G III/II/I 模式
        un_num = re.search(r'UN\s+\d+\b', text)
        if un_num:
            after_un = text[un_num.end():un_num.end() + 200]
            if re.search(r'\b\d+(?:\.\d+)?\s+P\s*G\s+[IVXL]+\b', after_un):
                return "DG"

        # 兜底3：检测 PSN 行中的 NOT REGULATED / NOT RESTRICTED → NDG
        # 有些 PDF 使用表头格式 "UN No. Description ..."，没有标准的 UN 数字行
        # 但会有 PSN 行标记物品性质
        psn_match = re.search(r'PSN:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if psn_match:
            psn_text = psn_match.group(1).upper()
            if 'NOT REGULATED' in psn_text or 'NOT RESTRICTED' in psn_text:
                return "NDG"

        # 兜底4：检测文本中是否包含明确的 DG/NDG 标记（在非产品编码上下文中）
        # 避免匹配产品编码中的 DG 子串（如 BYPWB1DG02）
        # 在 UN 数据区域附近（而非产品编码行）找独立出现的 DG/NDG
        un_area = re.search(r'UN\s+(?:No\.?\s*Description|None|\d+)', text, re.IGNORECASE)
        if un_area:
            area_start = un_area.start()
            area_end = min(len(text), area_start + 500)
            area_text = text[area_start:area_end]
            # 排除产品编码行（含数字字母组合或以数字结尾的长编码行）
            lines = area_text.split('\n')
            for line in lines:
                line_upper = line.strip().upper()
                # 独立 DG/NDG 标记（非产品编码上下文）
                if re.search(r'(?:^|\s)(DG|NDG)(?:\s|$)', line_upper):
                    return 'DG' if 'DG' in line_upper and 'NDG' not in line_upper else 'NDG'

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
        result = ""

        # ── 策略1：从收货地址/交货至标签提取 ─────────────────────
        result = ContentParser.extract_block(
            text, ["收货地址:", "收货地址：", "交货至:", "交货至："],
            ["订单号", "电话", "传真", "客户联系人", "Waybill"]
        )

        # ── 策略2：从客户：标签提取（截取到Frt bill前 + 电话行） ──
        if not result:
            raw_block = ContentParser.extract_block(
                text, ["客户:", "客户："],
                ["运输公司", "Carrier", "发货单号", "客户联系人"]
            )
            if raw_block:
                lines = [ln.strip() for ln in raw_block.splitlines() if ln.strip()]

                # 地址区域的结束：取 Frt bill 往后的所有行
                # （因为地址可能在Frt bill前的公司名行，也可能在Frt bill后的电话/传真行）
                addr_end = len(lines)
                for i, line in enumerate(lines):
                    if re.search(r'客户联系人', line):
                        addr_end = i
                        break
                    if re.search(r'运输公司承运人', line):
                        addr_end = i
                        break

                address_lines = lines[0:addr_end]
                if address_lines:
                    result = " ".join(address_lines)

        # ── 清洗 ──
        if result:
            r = result

            # 去英文/日期行
            r = re.sub(r'^.*?实际发货\s*[:：]\s*[A-Za-z]+\s+\d+,\s*\d{4}\s*', '', r)
            # 去公司名（先保护全角括号内的公司名，避免被误删）
            # 如"（宁波中骏森驰汽车零部件有限公司）"应保留
            protected = {}
            def _protect(m):
                k = f'__B{len(protected)}__'
                protected[k] = m.group(0)
                return k
            r = re.sub(r'（[^）]+有限公司[^）]*）', _protect, r)
            # 去公司名 — 但地址行中的客户公司名（如"嘉兴敏惠XX 10号仓库"）应保留
            # 保护 "XXX有限公司 数字号仓库" 类型的地址末尾
            protected_addr_end = {}
            def _protect_addr(m):
                k = f'__AD{len(protected_addr_end)}__'
                protected_addr_end[k] = m.group(0)
                return k
            r = re.sub(r'[\u4e00-\u9fa5]{2,40}(?:有限公司|股份公司)\s+\d+号\s*\w+', _protect_addr, r)

            r = re.sub(r'[\u4e00-\u9fa5（）]{2,40}(?:有限公司|股份公司|仓储有限|科技有限|月结库)\s*', '', r)
            r = re.sub(r'(?:^|\s)有限公司\s*', ' ', r)

            for k, v in protected_addr_end.items():
                r = r.replace(k, v)
            for k, v in protected.items():
                r = r.replace(k, v)
            # 去标签
            r = re.sub(r'Frt bill\s*[:：]\s*SBU\s*[:：]\s*[A-Za-z0-9]+', ' ', r)
            # 电话/传真正则限定匹配到可选空格+数字/连字符/空格结尾，不跨越到后面的英文单词
            r = re.sub(r'(?:电话|传真|SBU)[:：]\s*[\d\-\s]+(?:\s|$)', ' ', r)
            r = re.sub(r'Waybill[:：]?\s*', ' ', r, flags=re.IGNORECASE)
            r = re.sub(r'订单号[:：]\s*[A-Za-z0-9]+', ' ', r)
            r = re.sub(r'DONGGUAN\s*JUNZHE|SHANGHAI\s*XIANGYUE|PPG\s*COATINGS\s*TIANJIN\s*', ' ', r, flags=re.IGNORECASE)
            r = re.sub(r'CHANGSHU\s*RESUPPLY\s*WHSE[~]?\s*', ' ', r, flags=re.IGNORECASE)
            r = re.sub(r'XIAN\s*CHENGDA\s*DG\s*RESUPPLY\s*', ' ', r, flags=re.IGNORECASE)
            r = re.sub(r'BYD\s*HEFEI\s*CONS\s*WHSE[~]?\s*', ' ', r, flags=re.IGNORECASE)
            r = re.sub(r'JIAXING\s*YUJIA[~]?\s*', ' ', r, flags=re.IGNORECASE)
            r = re.sub(r'[A-Z\s.]{3,40}~', ' ', r)
            # ~ 后跟公司名/仓库名类关键词时删除，但不删除地址（地址不含"有限/股份/仓储/月结"等）
            r = re.sub(r'~[\u4e00-\u9fa5]{2,30}(?:有限公司|股份公司|仓储|科技|月结|汽车零部件|饰件|实业|电子|材料|包装)', ' ', r)
            r = re.sub(r'~\s+[\u4e00-\u9fa5]{2,30}(?:有限公司|股份公司|仓储|科技|月结|汽车零部件|饰件|实业|电子|材料|包装)', ' ', r)
            # 去仓库名残片（如"常熟仓库"、"西安DG RESUPPLY仓库"、"PPG 天津烟台仓库"）
            r = re.sub(r'(?:^|\s)(?:WHSE~)?[A-Z]*\s*[\u4e00-\u9fa5]{2,10}(?:DG\s*)?RESUPPLY\s*仓库', ' ', r, flags=re.IGNORECASE)
            r = re.sub(r'(?:^|\s)[\u4e00-\u9fa5]{2,6}仓库\s*', ' ', r)
            r = re.sub(r'(?:^|\s)PPG\s*[\u4e00-\u9fa5]{2,10}仓库\s*', ' ', r, flags=re.IGNORECASE)
            # 去PPG 限公司残片
            r = re.sub(r'(?:^|\s)PPG\s*限公司\s*', ' ', r, flags=re.IGNORECASE)
            # 去开头/中间独立的PPG（如烟台中的"PPG 山东省..."）
            r = re.sub(r'(?:^|\s)PPG\s+(?=[\u4e00-\u9fa5])', ' ', r, flags=re.IGNORECASE)
            # 去运输公司/承运商/批准人/联系人等标签行（包含乱码）
            r = re.sub(r'运输公司承运人[：:][^。\n]*?(?:客户|PPG|发货|\d)', ' ', r)
            r = re.sub(r'运\s*Ca\s*输\s*rri\s*公\s*er\s*司承运人[：:][^。\n]*', ' ', r)
            r = re.sub(r'客\s*P\s*户\s*G\s*联\s*联\s*系\s*系\s*人\s*人[：:][^。\n]*', ' ', r)
            r = re.sub(r'PPG联系人[：:][^。\n]*', ' ', r)
            r = re.sub(r'Org/Warehouse[：:][^。\n]*', ' ', r)
            r = re.sub(r'客户签收[：:][^。\n]*', ' ', r)
            r = re.sub(r'Customer\s*Receive[^。\n]*', ' ', r, flags=re.IGNORECASE)
            r = re.sub(r'操作人[：:]\s*\S+', ' ', r)
            r = re.sub(r'客户[：:]\s*\d+', ' ', r)
            r = re.sub(r'Cust Po[：:][^。\n]*', ' ', r)
            # 去城市行/CN行（只匹配到第一个逗号前为2~6个汉字的短城市名）
            r = re.sub(r'(?:^|\s)[\u4e00-\u9fa5]{2,6},\s*[\u4e00-\u9fa5]{2,6},\s*\d{4,6},\s*CN', ' ', r)
            # 压缩空格
            r = re.sub(r'\s+', ' ', r).strip()
            r = re.sub(r'^[:：\s]+', '', r)
            # 去非地址文本（送货备注、随货要求等）
            r = re.sub(r'送货时需携带客户送货单', '', r)
            r = re.sub(r'随货必带[^，。\n]*', '', r)
            r = re.sub(r'，批次板', '', r)
            r = re.sub(r'携带\d+份发货单', '', r)
            r = re.sub(r'\s*\(随货携带[^)]*\)', '', r)
            r = re.sub(r'\s*\(随货携带[^）]*\)', '', r)
            r = re.sub(r'发货需要携带[^，。\n]*', '', r)
            r = re.sub(r'不需要湿[^，。\n]*', '', r)
            r = re.sub(r's*\bCV\b[^，。\n]*', '', r, flags=re.IGNORECASE)
            # 去掉备注类全角括号内容（如"（随货携带COA…）"），但保留机构名括号（如"（宁波中骏森驰…）"）
            # 规则：括号内若含"随货/携带/标签/Cust Po/订单号"等备注词 → 删除整个括号
            r = re.sub(r'（[^）]*(?:随货|携带|COA|标签|批次板|保质期|Cust Po|订单号)[^）]*）', '', r)
            # 去掉半角括号备注（如"(随货携带…)"）
            r = re.sub(r'\([^)]*(?:随货|携带|COA|标签|批次板|保质期)[^)]*\)', '', r)
            # 去括号只留内容（括号内是机构名/公司名）
            r = re.sub(r'（([^）]+(?:有限公司|股份公司|仓储有限|科技有限)[^）]*)）', r'\1', r)
            r = re.sub(r'\s+', ' ', r).strip()
            r = re.sub(r'\s+([\u4e00-\u9fa5])$', '', r).strip()
            r = re.sub(r'，\s*$', '', r).strip()
            r = re.sub(r'\s*,\s*$', '', r).strip()
            # 补省前缀：如"宁波慈溪市…"前加"浙江省"
            r = re.sub(r'^(宁波|湖州|嘉兴|杭州|绍兴)', r'浙江省\1', r)

            result = r

        # ── 策略3：如果策略2没得到有效地址，从传真/电话行提取 ──
        if not result:
            fax_pos = text.find('传真：')
            if fax_pos == -1:
                fax_pos = text.find('传真:')
            if fax_pos != -1:
                after_fax = text[fax_pos:]
                end_kws = ['批准人', '客户联系人', '运输公司', '承运商']
                end_pos = len(after_fax)
                for kw in end_kws:
                    p = after_fax.find(kw)
                    if p != -1 and p < end_pos:
                        end_pos = p
                fax_block = after_fax[:end_pos].strip()

                fax_clean = re.sub(r'^传真[:：][\d\s\-]+\s*', '', fax_block)
                fax_clean = re.sub(r'Waybill.*$', '', fax_clean).strip()
                fax_clean = re.sub(r'[\u4e00-\u9fa5a-zA-Z\s]+,\s*[\u4e00-\u9fa5a-zA-Z\s]+,\s*\d{4,6},\s*CN\s*', '', fax_clean)
                fax_clean = re.sub(r'\s+', ' ', fax_clean).strip()

                if fax_clean:
                    # 基本清洗
                    fax_clean = re.sub(r'[\u4e00-\u9fa5（）]{2,40}(?:有限公司|股份公司|仓储有限)\s*', '', fax_clean)
                    fax_clean = re.sub(r'\s+', ' ', fax_clean).strip()
                    # 只要包含地址特征就用
                    if re.search(r'[省市区县路街道]', fax_clean):
                        result = fax_clean

        if result:
            logger.info(f"提取 [地址] -> 成功: True | 内容: {result}")
        else:
            logger.info("提取 [地址] -> 成功: False | 内容: ")
        return result

    @staticmethod
    def extract_requirement(text: str) -> str:
        result = ContentParser.extract_block(
            text, 
            ["客户要求"], 
            ["批准人", "UN No.", "UN None", "Description", "Item Ord.Qty", "Shipped Qty", "总毛重"]
        )
        if result:
            # 去掉末尾紧跟的订单号（如 "自提 11973589" → "自提"）
            result = re.sub(r'\s+11\d{6,}$', '', result).strip()
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
        pdf_danger = ContentParser.extract_danger_from_pdf(norm_text)

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
            "pdf_danger": pdf_danger,
        }

