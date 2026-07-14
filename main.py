import os
import logging
from utils.config import load_config
from mail.mail_reader import MailReader
from parser.pdf_parser import PDFParser
from parser.content_parser import ContentParser
from business.rule_engine import RuleEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting PPG WH Agent...")
    config = load_config()
    
    # 1. 邮件读取
    # reader = MailReader(...)
    
    # 2. 提取附件 (PDF) 并解析
    # pdf_parser = PDFParser()·87
    
    # 3. 内容解析 (文本/表格提取，后续作为飞书智能体 Skill 的输入)
    # content_parser = ContentParser()
    
    # 4. 业务规则引擎处理
    # rule_engine = RuleEngine()
    
    # 5. 结果保存 (例如保存到 output 目录的 JSON)

if __name__ == "__main__":
    main()
