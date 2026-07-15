import sys
import os
import json
import logging
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parser.content_parser import ContentParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_parse_pdf_fields():
    print("=== 测试: PDF 长短文本解析提取 ===")
    
    # 情况1
    text1 = """
    订单号: 419624
    客户要求：发货需要带COA色板，新批次需要提供1L小样，随货携带
    客户签收：
    数量: 22
    总毛重 : 875.000KG
    """
    
    # 情况2
    text2 = """
    计划发货: July 15, 2026
    订单号： 123456
    客户要求
    发货需要带COA
    色板新批次需要提供1L小样
    随货携带
    数量 : 22
    总毛重: 100.5KG
    联系人
    杜勇 -19962830255
    电话
    """
    
    # 情况3
    text3 = """
    订单号: 789012
    客户要求：
    发货需要带COA色板
    
    新批次需要提供1L
    
    小样
    
    随货携带
    
    数量
    22
    总毛重 : 50KG
    """

    texts = [text1, text2, text3]
    for i, t in enumerate(texts, 1):
        print(f"\n--- 测试情况 {i} ---")
        result = ContentParser.parse_pdf_text(t)
        print("提取结果:")
        print(json.dumps(result, ensure_ascii=False, indent=4))

if __name__ == "__main__":
    test_parse_pdf_fields()
