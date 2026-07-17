# pyrefly: ignore [missing-import]
import pdfplumber
import logging

logger = logging.getLogger(__name__)

class PDFParser:
    @staticmethod
    def parse_pdf(file_path: str) -> str:
        """
        提取 PDF 所有文字，按页面顺序拼接为字符串。
        如果当前页面包含 "总毛重"，则停止继续读取后面的页面。
        """
        text_content = []
        
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_num = i + 1
                    logger.info(f"读取第 {page_num} 页: {file_path}")
                    
                    text = page.extract_text()
                    
                    # 避免空页
                    if not text:
                        continue
                        
                    text_content.append(text)
                    
                    # 停止条件
                    if "总毛重" in text:
                        logger.info(f"在第 {page_num} 页检测到 '总毛重'，停止读取后续页面。")
                        break
                        
            return "\n".join(text_content)
            
        except Exception as e:
            logger.error(f"解析 PDF 出错 {file_path}: {e}")
            return ""
