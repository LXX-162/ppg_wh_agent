import logging
from feishu.bitable import BitableClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting sync to Feishu Bitable...")
    # client = BitableClient(...)
    # 读取 output 目录下的 JSON 并同步到飞书多维表

if __name__ == "__main__":
    main()
