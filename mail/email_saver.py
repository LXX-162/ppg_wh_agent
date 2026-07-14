import os
import logging

logger = logging.getLogger(__name__)

class EmailSaver:
    def __init__(self, output_dir="file/"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def save_attachment(self, filename, content):
        """保存邮件附件到本地"""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(content)
        logger.info(f"Saved attachment to {filepath}")
        return filepath

    def save_body(self, filename, content):
        """保存邮件正文文本到本地供调试"""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Saved email body to {filepath}")
        return filepath
