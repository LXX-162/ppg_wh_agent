import os
import requests
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()
from feishu.bitable import BitableClient

client = BitableClient(os.getenv('FEISHU_APP_ID'), os.getenv('FEISHU_APP_SECRET'))
client._get_tenant_access_token()
app_token = os.getenv("FEISHU_BITABLE_APP_TOKEN")
url = f'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables'
res = requests.get(url, headers={'Authorization': f'Bearer {client.tenant_access_token}'})
print(res.json())
