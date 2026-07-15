import sys
import os
import logging
import io

# 强制控制台输出使用 utf-8 编码，防止 Windows GBK 报错
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from utils.config import load_config
from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter
from mail.email_saver import save_attachments
from parser.pdf_parser import PDFParser
from parser.content_parser import ContentParser
from utils.cache_manager import CacheManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting PPG WH Agent Flow...")
    
    # 1. 初始化和加载缓存
    shipping_cache = CacheManager.load_cache()
    logger.info(f"已加载本地发货缓存，当前缓存订单数量: {len(shipping_cache)}")
    
    reader = MailReader()
    
    try:
        # 获取最近 15 封邮件进行测试
        mails = reader.fetch_recent(limit=15)
        logger.info(f"成功获取 {len(mails)} 封最近的邮件，开始分类处理...")
        
        pdf_process_count = 0
        
        for m in mails:
            uid = m["uid"]
            msg = m["message"]
            mail_type = MailFilter.get_type(m)
            
            if mail_type == "SHIPPING_INFO":
                logger.info(f"-> [UID {uid}] 检测到 SHIPPING_INFO (发货邮件)")
                # 提取正文
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
                
                # 解析表格
                new_shipping_data = ContentParser.parse_shipping_mail(m.get("subject", ""), body)
                if new_shipping_data:
                    logger.info(f"解析出发货数据: {len(new_shipping_data)} 条订单记录")
                    shipping_cache.update(new_shipping_data)
                    # 实时保存缓存
                    CacheManager.save_cache(shipping_cache)
                    
            elif mail_type == "PDF_ORDER":
                logger.info(f"-> [UID {uid}] 检测到 PDF_ORDER (订单邮件)")
                
                # 为了快速测试，我们控制一下最多只实际处理 2 封带 PDF 的邮件
                if pdf_process_count >= 2:
                    logger.info(f"已达到测试设置的 PDF 解析上限(2封邮件)，跳过 [UID {uid}] 避免跑太久")
                    continue
                    
                # 保存附件
                saved_pdfs = save_attachments(uid, msg)
                
                # 解析提取刚才保存的 PDF
                for pdf_path in saved_pdfs:
                    logger.info(f"正在抽取文本: {pdf_path}")
                    pdf_text = PDFParser.parse_pdf(pdf_path)
                    logger.info(f"文本抽取完成，长度: {len(pdf_text)} 字符")
                    
                pdf_process_count += 1
                
            else:
                pass # 对于 UNKNOWN 邮件，直接跳过，不输出日志以免刷屏
                
        logger.info("=== 运行流水线测试完成 ===")
        logger.info(f"当前最新的 Shipping 缓存数量: {len(shipping_cache)}")
        
    except Exception as e:
        logger.error(f"执行异常: {e}")
    finally:
        reader.disconnect()

if __name__ == "__main__":
    main()
