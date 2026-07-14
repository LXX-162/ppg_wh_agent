import logging
from utils.config import load_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Running debug tool to save latest emails locally...")
    # 此脚本用于快速拉取最新 N 封邮件的正文和附件并保存到本地
    # 方便开发阶段测试 PDF 解析和内容提取逻辑

if __name__ == "__main__":
    main()
