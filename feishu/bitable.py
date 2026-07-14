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
