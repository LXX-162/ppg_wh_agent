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
            req_contact = cls._extract_contact_from_text(requirement, is_requirement=True)

        # 2. 从原 contact 字段提取并清理
        base_contact = ""
        if contact:
            # 清理杂音
            contact = re.sub(r'[\s\n]*操作人[:：\s]*[A-Za-z0-9_]+', '', contact)
            contact = re.sub(r'[\s\n]*Carrier.*', '', contact)
            
            # 使用提取器进行精准提纯
            extracted = cls._extract_contact_from_text(contact, is_requirement=False)
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

        # 4. 兜底：若仍提取不出任何联系人，只要在"客户要求/客户联系人"源文本
        #    中看到电话号码格式就写入，保证联系人字段不为空。
        if not final_contacts:
            source = f"{requirement} {order.get('contact','')}".strip()
            if source:
                phone_only = cls._extract_contact_from_text(source, is_requirement=True)
                if phone_only:
                    final_contacts.append(phone_only)
                    logger.info(f"[Rule: Contact] 兜底：从客户要求/客户联系人提取到电话 -> {phone_only}")

        # 5. 去重：同一联系人的电话可能有不同格式（"156 188 2 7168" vs "15618827168"），
        #    以去空格后的字符串为唯一键，避免同一个人字重复出现。
        dedup = []
        seen_keys = set()
        for c in final_contacts:
            key = re.sub(r'\s', '', c)
            if key and key not in seen_keys:
                seen_keys.add(key)
                dedup.append(c)
        final_contacts = dedup

        order["contact"] = " ".join(final_contacts).strip()
        return order

    @classmethod
    def _extract_contact_from_text(cls, text: str, is_requirement: bool = False) -> str:
        # 手机号支持 3-4-4 分段空格/连字符（如 156 1882 7168 / 156-1882-7168），
        # 亦兼容连续 11 位；固话保持原匹配
        mobile = r'1[3-9]\d(?:[\s\-]?\d){8}'
        tel    = r'0\d{2,3}-?\d{7,8}(?:-\d{1,4})?'
        # 单个电话体（手机或固话）
        phone_body = rf'(?:{mobile}|{tel})'
        # 多电话连接（用逗号/斜杠/分号，避免用纯空格连接——因为手机号内部允许空格会发生歧义）
        multi_phone_pattern = rf'(?:{phone_body})(?:\s*[,，、;；/]\s*{phone_body})*'

        contacts = []
        working_text = text

        # 策略 1: 带有明确动词或前缀的名字+电话
        p_exact = re.compile(rf'(?:签收人(?:是)?|收货人(?:是)?|联系人(?:是)?|收件人[:：]?|采购(?:是)?|通知|交给|联系|找)[\s:]*([A-Za-z\u4e00-\u9fa5]{{1,20}}(?:(?:\s+|/)[A-Za-z\u4e00-\u9fa5]{{1,10}})*)(?:[A-Za-z0-9\s,，\-_]*)(?:联系电话|电话|手机)?[\s:：，,]*({multi_phone_pattern})')
        for match in p_exact.finditer(working_text):
            name = match.group(1).strip()
            # 简单清理一下由于英文匹配贪婪导致带上的乱码
            name = re.sub(r'\s+(?:GW|PN|ID|No).*$', '', name, flags=re.IGNORECASE)
            phone = match.group(2).strip()
            contacts.append(f"{name} {phone}")
            working_text = working_text.replace(match.group(0), " " * len(match.group(0)))

        # 策略 1.5: 姓名在电话号码之后（如 "手机：156 1882 7168 孙泽龙"）。
        # 前缀（手机/电话/联系）可选；电话后允许粘连姓名与干扰词（如"孙泽龙色浆"）。
        strip_noise = re.compile(r'[色浆包装使用要求备注需要发货批次电话手机地址送到前台送达营业部仓库订单]+$')
        p_phone_name = re.compile(
            rf'(?:联系电话|电话|手机|联系)?[\s:：，,]*({phone_body})[\s，,:：]*([\u4e00-\u9fa5]{{2,6}})'
        )
        for match in p_phone_name.finditer(working_text):
            phone = match.group(1).strip()
            name = match.group(2).strip()
            # 姓名最多保留 4 字（防止把后面正文一并吞入），再去掉尾部粘连的
            # 干扰词（如 "孙泽龙色浆" -> "孙泽龙"，"李伟地址" -> "李伟"）
            name = name[:4]
            name = strip_noise.sub('', name)
            # 过滤非人名干扰词
            if name and len(name) >= 2 and not any(w in name for w in ["需要", "批次", "发货", "要求",
                                                    "电话", "手机", "送达", "地址", "拨打", "送到",
                                                    "前台", "包装", "色浆", "使用", "公司", "股份"]):
                # 姓名置前
                contacts.append(f"{name} {phone}")
                working_text = working_text.replace(match.group(0), " " * len(match.group(0)))

        # 策略 2: 名字直接跟着电话号码的启发式
        p_heuristic = re.compile(rf'([A-Za-z\u4e00-\u9fa5]{{2,15}}(?:/[A-Za-z\u4e00-\u9fa5]{{1,10}})?)(?:[\s,，:：\-A-Za-z0-9_]*)(?:联系电话|电话|手机)?[\s:：，,]*({multi_phone_pattern})')
        for match in p_heuristic.finditer(working_text):
            name = match.group(1).strip()
            phone = match.group(2).strip()
            
            # 剥离前面可能连着的地址残余 (比如 "路郁海亮" -> "郁海亮")
            name = re.sub(r'^[^\u4e00-\u9fa5A-Za-z]*(?:公司|省|市|区|镇|路|号|厂|街|道|楼|层|室|开发区|园区)+', '', name)
            
            # 过滤掉非人名的常见词汇组合
            if not any(w in name for w in ["需要", "批次", "发货", "备注", "要求", "电话", "手机", "送达", "地址", "到达", "拨打", "送到", "前台"]):
                if len(name) > 1 and len(name) <= 15:
                    contacts.append(f"{name} {phone}")
                    working_text = working_text.replace(match.group(0), " " * len(match.group(0)))
            
        # 策略 3: 如果还是没有任何名字，退回到仅仅提取电话号码
        p_phone_only = re.compile(multi_phone_pattern)
        for match in p_phone_only.finditer(working_text):
            phone = match.group(0).strip()
            contacts.append(phone)
            working_text = working_text.replace(match.group(0), " " * len(match.group(0)))
            
        # 策略 4: 被 PDF 排版打碎的电话号码 (例如 "张-18东0东..." -> 名字被插在数字里)
        # 仅对 contact 字段使用这种激进的兜底策略，因为 requirement 字段中可能包含很多无关中文字符和数字
        if not contacts and not is_requirement:
            all_digits = re.sub(r'\D', '', working_text)
            if len(all_digits) in [11, 22]:
                all_chinese = re.sub(r'[^\u4e00-\u9fa5]', '', working_text)
                if len(all_digits) == 11:
                    contacts.append(f"{all_chinese} {all_digits}".strip())
                elif len(all_digits) == 22:
                    p1 = all_digits[:11]
                    p2 = all_digits[11:]
                    contacts.append(f"{all_chinese} {p1} {p2}".strip())
            
        # 去重并组装
        result = []
        for c in contacts:
            if c not in result and c:
                result.append(c)
                
        return " ".join(result)
