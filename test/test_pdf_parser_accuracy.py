import sys
import os
import glob
import logging
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parser.pdf_parser import PDFParser
from parser.content_parser import ContentParser

# 暂时屏蔽解析器内部自带的 INFO 日志，以免扰乱格式化的 print 输出
logging.getLogger("parser.content_parser").setLevel(logging.WARNING)
logging.getLogger("parser.pdf_parser").setLevel(logging.WARNING)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

def test_accuracy():
    pdf_dir = os.path.join(os.path.dirname(__file__), "..", "file", "pdf")
    if not os.path.exists(pdf_dir):
        print(f"目录 {pdf_dir} 不存在。")
        return
        
    pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf"))
    total_pdfs = len(pdf_files)
    
    if total_pdfs == 0:
        print(f"在 {pdf_dir} 没有找到 PDF 文件。")
        return
        
    stats = {
        "order_no": 0,
        "order_date": 0,
        "contact": 0,
        "requirement": 0,
        "address": 0,
        "quantity": 0,
        "weight": 0
    }
    
    label_map = {
        "order_no": "订单号",
        "order_date": "日期",
        "contact": "联系人",
        "requirement": "客户要求",
        "address": "地址", 
        "quantity": "数量",
        "weight": "重量"
    }

    print(f"找到 {total_pdfs} 个 PDF，开始批量解析...\n")

    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        print("====================")
        print(f"文件名: {filename}")
        
        try:
            # 提取PDF纯文本
            raw_text = PDFParser.parse_pdf(pdf_path)
            # 解析结构化字段
            result = ContentParser.parse_pdf_text(raw_text)
            
            print(f"订单号：{result.get('order_no', '')}")
            print(f"日期：{result.get('order_date', '')}")
            print(f"收货单位：")  # 暂无专门的解析逻辑，留空占位
            print(f"收货地址：{result.get('address', '')}")
            print(f"联系人：{result.get('contact', '')}")
            
            # 把客户要求的换行替换为空格，避免打乱排版
            req = result.get('requirement', '').replace('\n', ' ')
            print(f"客户要求：{req}")
            
            print(f"数量：{result.get('quantity', '')}")
            print(f"重量：{result.get('weight', '')}")
            print("====================\n")
            
            # 统计成功率
            for k in stats.keys():
                if result.get(k):  # 只要不是空字符串就算成功
                    stats[k] += 1
                    
        except Exception as e:
            print(f"解析 {filename} 出错: {e}")
            print("====================\n")

    # 打印最终统计
    print("=" * 20)
    print(f"统计：总共解析 {total_pdfs} 个PDF。")
    print("每个字段成功率：")
    for key, label in label_map.items():
        success_count = stats[key]
        rate = (success_count / total_pdfs) * 100
        print(f"{label}：{rate:.0f}%")
    print("=" * 20)

if __name__ == "__main__":
    test_accuracy()
