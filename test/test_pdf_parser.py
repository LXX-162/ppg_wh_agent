import sys
import os
import json
import logging
import io

# 强制控制台输出使用 utf-8 编码，防止 Windows GBK 报错
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parser.pdf_parser import PDFParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_pdf_parser():
    # 找一个现有的 PDF 进行测试（刚刚下载到 file/pdf/ 目录下的某个文件）
    pdf_dir = os.path.join("file", "pdf")
    
    if not os.path.exists(pdf_dir):
        print(f"目录不存在: {pdf_dir}")
        return
        
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print("未找到任何 PDF 文件进行测试。")
        return
        
    # 取第一个 PDF 文件
    test_pdf = os.path.join(pdf_dir, pdf_files[0])
    print(f"正在测试 PDF 文件: {test_pdf}")
    print("-" * 50)
    
    # 提取文字
    result = PDFParser.parse_pdf(test_pdf)
    
    print("-" * 50)
    print("返回结果 json.dumps 形式:")
    # 打印被转义的原始内容，方便检查字段是否都正常被读取到
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    test_pdf_parser()
