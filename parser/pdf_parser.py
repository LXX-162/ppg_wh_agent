import pdfplumber
import logging

logger = logging.getLogger(__name__)

class PDFParser:
    def __init__(self):
        pass

    def parse_pdf(self, file_path):
        """解析PDF文件，提取文本和表格。由于要求含有表格即文字说明，此方法主要提取纯文本供大模型或正则处理。"""
        logger.info(f"Parsing PDF: {file_path}")
        text_content = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_content.append(text)
            return "\n".join(text_content)
        except Exception as e:
            logger.error(f"Error parsing PDF {file_path}: {e}")
            return ""
