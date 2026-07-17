import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()
from feishu.bitable import BitableClient

client = BitableClient(os.getenv('FEISHU_APP_ID'), os.getenv('FEISHU_APP_SECRET'))
records = client.get_records(os.getenv("FEISHU_BITABLE_APP_TOKEN"), os.getenv("FEISHU_RECEIVER_TABLE_ID"))
print(f"Total records: {len(records)}")
for i, r in enumerate(records[:10]):
    print(r.get('fields'))
