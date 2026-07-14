import logging

logger = logging.getLogger(__name__)

class ContentParser:
    def __init__(self):
        pass

    def extract_order_info(self, subject, body, pdf_text):
        """
        内容解析器，整合邮件主题、正文和 PDF 文本内容。
        该项目后续作为飞书智能体 Skill，所以这里主要做内容整合或初步正则匹配。
        """
        logger.info("Extracting order info from content...")
        
        # 整合为一段文本或结构化数据返回，供智能体分析
        combined_text = f"【主题】\n{subject}\n\n【正文】\n{body}\n\n【附件PDF】\n{pdf_text}"
        
        return {
            "raw_combined_text": combined_text,
            # 可以添加简单的正则解析逻辑
        }
