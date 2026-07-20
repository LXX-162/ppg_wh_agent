import logging
import requests

logger = logging.getLogger(__name__)

class BitableClient:
    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_access_token = None

    def _get_tenant_access_token(self):
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 0:
                self.tenant_access_token = data.get("tenant_access_token")
                logger.info("Successfully got tenant_access_token")
            else:
                logger.error(f"Failed to get tenant_access_token: {data.get('msg')}")
        except Exception as e:
            logger.error(f"Exception when getting tenant_access_token: {e}")

    def write_records(self, app_token, table_id, records):
        """批量写入记录到多维表"""
        if not self.tenant_access_token:
            self._get_tenant_access_token()
            
        if not self.tenant_access_token:
            logger.error("No valid tenant_access_token, abort writing.")
            return False

        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json"
        }
        
        # 将 records 转换为飞书要求的格式
        # 飞书格式: [{"fields": {"客户名": "xxx", "单号": "xxx"}}, ...]
        feishu_records = [{"fields": record} for record in records]
        
        payload = {
            "records": feishu_records
        }
        
        try:
            logger.info(f"Writing {len(records)} records to table {table_id}")
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 0:
                logger.info("Successfully wrote records to Feishu.")
                return True
            else:
                logger.error(f"Failed to write records: {data.get('msg')}")
                return False
        except Exception as e:
            logger.error(f"Exception when writing records to Feishu: {e}")
            return False

    def get_records(self, app_token, table_id):
        """拉取多维表中的所有记录"""
        if not self.tenant_access_token:
            self._get_tenant_access_token()
            
        if not self.tenant_access_token:
            logger.error("No valid tenant_access_token, abort reading.")
            return []

        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}"
        }
        
        all_records = []
        page_token = ""
        has_more = True
        
        while has_more:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
                
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                if data.get("code") == 0:
                    items = data.get("data", {}).get("items", [])
                    all_records.extend(items)
                    
                    has_more = data.get("data", {}).get("has_more", False)
                    page_token = data.get("data", {}).get("page_token", "")
                else:
                    logger.error(f"Failed to get records: {data.get('msg')}")
                    break
            except Exception as e:
                logger.error(f"Exception when getting records from Feishu: {e}")
                break
                
        return all_records

    def delete_records_by_date(self, app_token: str, table_id: str, date_str: str) -> int:
        """
        删除多维表中 下单日期 == date_str 的所有记录。
        date_str 格式：YYYY/MM/DD 或 YYYY-MM-DD（与多维表字段中存储的格式对应）。
        返回实际删除的记录数。
        """
        if not self.tenant_access_token:
            self._get_tenant_access_token()
        if not self.tenant_access_token:
            logger.error("No valid tenant_access_token, abort delete.")
            return 0

        # 1. 拉取所有记录
        all_records = self.get_records(app_token, table_id)
        logger.info(f"共拉取到 {len(all_records)} 条记录，开始筛选日期 == {date_str} 的记录...")

        # 2. 筛选匹配的 record_id
        # 飞书日期字段存储为毫秒时间戳，需要换算后比对
        # 也支持字段直接存储字符串的情况
        target_ids = []
        for rec in all_records:
            fields = rec.get("fields", {})
            field_val = fields.get("下单日期")
            match = False
            if isinstance(field_val, (int, float)):
                # 时间戳毫秒 → 日期字符串
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(field_val / 1000, tz=timezone.utc)
                rec_date = dt.strftime("%Y-%m-%d")
                # date_str 可能是 YYYY/MM/DD 或 YYYY-MM-DD，统一转换比较
                target_date = date_str.replace("/", "-")
                match = rec_date == target_date
            elif isinstance(field_val, str):
                match = field_val.replace("/", "-") == date_str.replace("/", "-")
            if match:
                target_ids.append(rec["record_id"])

        if not target_ids:
            logger.info(f"未找到日期为 {date_str} 的记录，无需删除")
            return 0

        logger.info(f"找到 {len(target_ids)} 条需要删除的记录")

        # 3. 分批删除（飞书限制每批最多 500 条）
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json"
        }
        deleted = 0
        BATCH = 500
        for i in range(0, len(target_ids), BATCH):
            batch = target_ids[i: i + BATCH]
            try:
                resp = requests.post(url, headers=headers, json={"records": batch})
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == 0:
                    deleted += len(batch)
                    logger.info(f"已删除 {deleted}/{len(target_ids)} 条记录")
                else:
                    logger.error(f"批量删除失败: {data.get('msg')}")
            except Exception as e:
                logger.error(f"批量删除异常: {e}")

        return deleted

