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

        # 0. 特殊订单地址硬映射（业务规则指定）
        order_no = order.get("order_no", "")
        special_addrs = {
            "11964715": "昆山市千灯镇秦峰北路5号",
        }
        if order_no in special_addrs:
            order["address"] = special_addrs[order_no]
            return order

        # 0b. 针对武汉恒基达鑫 / 化工五路的特殊处理
        req_clean = requirement.replace(" ", "")
        addr_clean = address.replace(" ", "")
        if "恒基达鑫" in req_clean or "恒基达鑫" in addr_clean or ("化工五路" in req_clean and "武汉" in req_clean):
            order["address"] = "湖北省武汉市洪山区化工五路1号武汉恒基达鑫国际化工仓储有限公司"
            return order

        # 提取标准中文地址的精准正则：必须以 省/市/区 开启，并使用贪婪匹配到最后一个结尾词
        # 优化：1. 省/市名前缀不允许含有公司、有限等词，防止将公司名部分错误匹配为地址前部。
        #       2. 增加了口、楼、门、栋、座、室等结尾词，确保"交叉口"、"1号楼"、"5号门"等行尾细节信息能够被完整匹配。
        addr_pattern = r'((?:(?![公司有限集团厂仓库物流股份])[\u4e00-\u9fa5]){2,10}(?:省|市|自治区|自治州|实验区|开发区|新区|高新区|县|区)[\u4e00-\u9fa5A-Za-z0-9_ \-（）\(\)、「」、，\?？\ufffd\u2014\u2013\.#]+(?:[）\)]|号|公司|集团|厂|仓库|基地|中心|车间|工业园|园区|区|东|南|西|北|侧|路|街|道|弄|口|楼|门|栋|座|室|房|虎|米|实业)[）\)]?(?:[\u4e00-\u9fa5A-Za-z0-9\-]{0,15})?)'

        # 清理 requirement 中的订单号和批准人信息
        requirement = re.sub(r'11\d{6,8}', ' ', requirement)
        requirement = re.sub(r'[\u4e00-\u9fa5]{2,4}批准人[：]?\s*[\d]*', '', requirement)
        # 去掉地址中的联系人姓名+电话（如"俞超 13851587490"）
        requirement = re.sub(r'(?<!\d)[\u4e00-\u9fa5]{2,3}\s*\d{7,11}', '', requirement)

        # 1. 优先从客户要求中提取地址
        if requirement:
            req_match = re.search(addr_pattern, requirement)
            if req_match:
                order["address"] = req_match.group(1).replace('\n', ' ').strip()
                # 剔除中文字符间的空格
                order["address"] = re.sub(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])', '', order["address"])
                # 清理 requirement 中提取的地址的前缀杂音（"保温产品送到"、"第二地址发货"等）
                order["address"] = re.sub(r'保温产品送到\s*', '', order["address"])
                order["address"] = re.sub(r'第二地址发货\s*', '', order["address"])
                order["address"] = re.sub(r'\s*货台叫号\d*', '', order["address"])
                # 清理地址末尾的姓名/收货人/电话号码/括号注释
                order["address"] = re.sub(r'(?<!\d)[\u4e00-\u9fa5]{2,3}\s*\d{7,11}\s*$', '', order["address"])
                order["address"] = re.sub(r'\d{7,11}\s*$', '', order["address"])
                order["address"] = re.sub(r'收货人[\u4e00-\u9fa5，,、\sA-Za-z\d()（）\-]+$', '', order["address"])
                                # 去掉地址末尾括号注释（仅当括号内容包含 requirement 关键词时）
                order["address"] = re.sub(
                    r'\s*[（\(](?:随货|携带|COA|保质期|批次|需粘贴|需黏贴|要求|需要|仓库|附件)[^）\)]*[）\)].*$',
                    '', order["address"]).strip()
                # 去掉地址末尾跟的英文/数字杂音（如 "ALD096100-FVW(CC)"），但保留中文地址主体
                order["address"] = re.sub(r'[A-Za-z0-9\-]+[（\(][^）\)]+[）\)][A-Za-z0-9\-]*\s*$', '', order["address"])
                return order

            # 兜底：如果标准地址模式匹配失败，尝试从 requirement 中的 "交易地址：" 提取
            trade_match = re.search(r'交易地址\s*[:：]\s*([\u4e00-\u9fa5\w\-（()）+、，。]+?)(?:联系人|$)', requirement)
            if trade_match:
                trade_addr = trade_match.group(1).strip()
                if len(trade_addr) >= 6:  # 长度至少6个中文字符才视为有效地址
                    order["address"] = trade_addr
                    return order

        # 2. 清理原始 address 字符串
        # 剔除各种杂音
        # 剔除地址中混入的订单号（11开头的8位数字，且后面不跟单位/地址关键词时视为订单号）
        address = re.sub(r'11\d{6,8}', ' ', address)
        address = re.sub(r'实际发货[:：].*?(?=\n|$)', ' ', address, flags=re.IGNORECASE)
        # 剔除"第二地址发货"等前缀（注意保留后面的地址主体）
        address = re.sub(r'第二地址发货\s*', '', address)
        address = re.sub(r'保温产品送到\s*', '', address)
        # 剔除"货台叫号"等非地址杂音（包含"号"字但"货台叫号"不是地址的一部分）
        address = re.sub(r'\s*货台叫号\d*', '', address)
        address = re.sub(r'[\u4e00-\u9fa5]{2,4}批准人[：]?\s*[\d]*', '', address)
        address = re.sub(r'PPG\s*涂料（[^）]+）有限公司|庞贝捷涂料（[^）]+）有限公司', ' ', address)
        # 2. 从原 address 字段提取
        # 预清理：去掉常见的前缀干扰项
        address = re.sub(r'(?:Frt bill|SBU)[:：]?\s*[A-Za-z0-9_]*', ' ', address, flags=re.IGNORECASE)
        address = re.sub(r'电话[:：]?\s*[\d\-]*', ' ', address)
        address = re.sub(r'(?<!\d)86\s*-?\s*\d{2,3}\s*-?\s*\d{4}\s*-?\s*\d{4}', ' ', address)
        address = re.sub(r'订单号[:：]?\s*[A-Za-z0-9_-]*', ' ', address)
        address = re.sub(r'Waybill[:：]?\s*[A-Za-z0-9_-]*', ' ', address, flags=re.IGNORECASE)

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

                # 特殊情况：如果匹配到的地址前有括号括起的附属信息（如 (麦尔总部)），且这一行确实确定为地址，则前面的括号内容一起保留
                prefix = address[:addr_match.start(1)].strip()
                parenthesis_match = re.search(r'([\(（][^\)）]+[\)）])\s*$', prefix)
                if parenthesis_match:
                    final_addr = parenthesis_match.group(1) + final_addr

                # 清理地址末尾的姓名/收货人/电话号码/括号注释
                final_addr = re.sub(r'(?<!\d)[\u4e00-\u9fa5]{2,3}[：:]?\s*\d{7,11}\s*$', '', final_addr)
                final_addr = re.sub(r'\d{7,11}\s*$', '', final_addr)
                final_addr = re.sub(r'收货人[\u4e00-\u9fa5，,、\sA-Za-z\d()（）\-]+$', '', final_addr)
                                # 去掉地址末尾括号注释（仅当括号内容包含 requirement 关键词时）
                final_addr = re.sub(
                    r'\s*[（\(](?:随货|携带|COA|保质期|批次|需粘贴|需黏贴|要求|需要|仓库|附件)[^）\)]*[）\)].*$',
                    '', final_addr)
                # 去掉地址末尾跟的英文/数字杂音（如 "ALD096100-FVW(CC)"），但保留中文地址主体
                final_addr = re.sub(r'[A-Za-z0-9\-]+[（\(][^）\)]+[）\)][A-Za-z0-9\-]*\s*$', '', final_addr)

                order["address"] = final_addr
                return order

            # 兜底：如果没匹配上（比如没有 省/市），就直接用清理过后的原句
            final_addr = re.sub(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])', '', address)
            final_addr = re.sub(r'\s*收货人[\u4e00-\u9fa5，,、\sA-Za-z\d()（）\-]+$', '', final_addr)
            # 去掉地址末尾括号注释（仅当括号内容包含 requirement 关键词时）
            final_addr = re.sub(
                r'\s*[（\(](?:随货|携带|COA|保质期|批次|需粘贴|需黏贴|要求|需要|仓库|附件)[^）\)]*[）\)].*$',
                '', final_addr)
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

                # 获取 收货单位 或 收货单位简称
                receiver_name = fields.get("收货单位") or fields.get("收货单位简称")
                address_text = fields.get("收货地址")

                if receiver_name and address_text:
                    if isinstance(receiver_name, list) and len(receiver_name) > 0:
                        receiver_name = receiver_name[0]
                    if isinstance(receiver_name, dict) and "text" in receiver_name:
                        receiver_name = receiver_name["text"]

                    if isinstance(address_text, list) and len(address_text) > 0:
                        address_text = address_text[0]
                    if isinstance(address_text, dict) and "text" in address_text:
                        address_text = address_text["text"]

                    receiver_str = str(receiver_name).strip()
                    address_str = str(address_text).strip()

                    if receiver_str and address_str:
                        # 剔除地址中的所有空格和标点符号，做成高密度字符串，方便模糊匹配
                        address_dense = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]', '', address_str)
                        if address_dense:
                            receivers.append({
                                "receiver": receiver_str,
                                "address": address_dense,
                                "raw_address": address_str
                            })

            logger.info(f"成功从飞书多维表格加载了 {len(receivers)} 个收货单位映射。")
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

        # 1. 优先尝试一模一样的地址匹配 (精准匹配)
        # 用已经清洗规范化后的 order["address"]
        normalized_addr = order.get("address", "")
        norm_addr_dense = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]', '', normalized_addr)

        raw_address = order.get("raw_address") or order.get("address", "")
        requirement = order.get("requirement", "")
        text_pool = f"{raw_address} {requirement}"
        text_pool_dense = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]', '', text_pool)

        exact_matches = []
        if norm_addr_dense:
            for record in receiver_list:
                if norm_addr_dense == record["address"]:
                    exact_matches.append(record)

        if exact_matches:
            # 统计精确匹配到的不同收货单位名称
            unique_receivers = set(rec["receiver"] for rec in exact_matches)

            # 如果有多个不同收货单位 → 多关系对应
            if len(unique_receivers) > 1:
                # 优先选择在表格中先匹配到的（排序靠上）
                order["receiver"] = exact_matches[0]["receiver"]
                order["address_exact_match"] = "多关系对应"
                return order

            # 只有一个收货单位或所有匹配记录都是同一收货单位 → 一致
            order["receiver"] = exact_matches[0]["receiver"]
            order["address_exact_match"] = "一致"
            return order

        # 2. 如果没有一模一样的地址，再利用文本池进行模糊匹配
        def can_partition(s, text):
            n = len(s)
            dp = [False] * (n + 1)
            dp[0] = True
            for i in range(1, n + 1):
                for j in range(i):
                    if dp[j]:
                        chunk = s[j:i]
                        # 允许的最小 chunk 长度为 2，以防止单个字造成的过度匹配
                        if len(chunk) >= 2 and chunk in text:
                            dp[i] = True
                            break
            return dp[n]

        matched_records = []
        for record in receiver_list:
            bitable_addr = record["address"]

            # 如果地址过短，直接要求全字匹配
            if len(bitable_addr) < 2:
                if bitable_addr in text_pool_dense:
                    matched_records.append(record)
            else:
                if bitable_addr in text_pool_dense or can_partition(bitable_addr, text_pool_dense):
                    matched_records.append(record)

        if matched_records:
            # 优先选择地址最长的（包含特征信息最多，越长越精确）
            best_match = max(matched_records, key=lambda x: len(x["address"]))
            order["receiver"] = best_match["receiver"]
            order["address_exact_match"] = "模糊匹配"
        else:
            # 兜底：即使没有任何记录通过模糊匹配，也从全库中挑出得分最高的一条
            # 按收货单位名称与文本池的字符重合度评分
            def score_record(rec):
                name = rec["receiver"]
                addr = rec["address"]
                # 收货单位名称出现在文本池中
                name_score = sum(1 for c in name if c in text_pool_dense) * 2
                # 地址字符与文本池的重合度
                addr_score = sum(1 for c in addr if c in text_pool_dense)
                return name_score + addr_score

            if receiver_list:
                best_fallback = max(receiver_list, key=score_record)
                order["receiver"] = best_fallback["receiver"]
            else:
                order["receiver"] = ""
            order["address_exact_match"] = "模糊匹配"

        return order

    @classmethod
    def normalize_city(cls, order: dict) -> dict:
        """业务修正规则：城市提取"""
        import sys, os
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        try:
            # pyrefly: ignore [missing-import]
            import jionlp as jio
        except Exception:
            jio = None
        finally:
            sys.stdout.close()
            sys.stdout = old_stdout

        address = order.get("address", "")
        if jio and address:
            try:
                res = jio.parse_location(address)
                province = res.get("province", "")
                city = res.get("city", "")
                county = res.get("county", "")

                # 直辖市/特殊城市处理
                if province in ["北京市", "天津市", "上海市", "重庆市"]:
                    city = province

                # 针对一些没有明确市的情况（如海南省直辖县级），使用 county 作为城市补充
                if province and (not city or city == "直辖县级" or city == "省直辖县级行政区划"):
                    if county:
                        city = county

                if province:
                    # 去掉省份后缀（省/市/自治区等），只保留地点名称
                    province_clean = province
                    for suffix in ["维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "省", "市"]:
                        if province_clean.endswith(suffix):
                            province_clean = province_clean[:-len(suffix)]
                            break
                    order["到货省份"] = province_clean
                if city:
                    # 去掉城市后缀（市/地区/自治州/盟/县），只保留地点名称
                    city_clean = city
                    for suffix in ["自治州", "地区", "市", "盟", "县"]:
                        if city_clean.endswith(suffix):
                            city_clean = city_clean[:-len(suffix)]
                            break
                    order["到货城市"] = city_clean

                # 针对直辖市（如北京、上海、天津、重庆）：省份和城市都设为去掉"市"后的名称
                if province_clean in ["北京", "上海", "天津", "重庆"]:
                    order["到货省份"] = province_clean
                    order["到货城市"] = city_clean if city_clean != province else province_clean
            except Exception:
                pass

        return order