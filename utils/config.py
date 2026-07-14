import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

def load_config():
    """加载 .env 配置文件"""
    load_dotenv()
    
    config = {
        "IMAP_HOST": os.environ.get("IMAP_HOST"),
        "IMAP_USER": os.environ.get("IMAP_USER"),
        "IMAP_PASS": os.environ.get("IMAP_PASS"),
        "FEISHU_APP_ID": os.environ.get("FEISHU_APP_ID"),
        "FEISHU_APP_SECRET": os.environ.get("FEISHU_APP_SECRET"),
    }
    
    # 验证关键配置是否存在
    for key, value in config.items():
        if not value:
            logger.warning(f"Configuration key '{key}' is missing or empty.")
            
    return config
