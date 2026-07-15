import sys
import os
import json
import logging
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from business.field_normalizer import FieldNormalizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_normalizer():
    print("=== 测试: normalize_contact() 业务修正规则 ===\n")
    
    # 构造不少于10个测试案例
    cases = [
        # 1. 联系人为空，要求里也没有联系人
        {
            "order_no": "C001",
            "contact": "",
            "requirement": "发货带COA色板，注意防潮。"
        },
        # 2. 联系人已有（不应被覆盖）
        {
            "order_no": "C002",
            "contact": "王五 13912345678",
            "requirement": "联系人：赵六 13800000000"
        },
        # 3. 只有手机号（无明确人名）
        {
            "order_no": "C003",
            "contact": "",
            "requirement": "到达后拨打 13800138000"
        },
        # 4. 只有固定电话
        {
            "order_no": "C004",
            "contact": "",
            "requirement": "公司前台 027-86500928"
        },
        # 5. 带有明确“电话”引导的
        {
            "order_no": "C005",
            "contact": "",
            "requirement": "浙江省宁波余姚市兰州路108号富诚零部件有限公司，储诚军，电话18055610324"
        },
        # 6. 带有明确“联系人”引导的
        {
            "order_no": "C006",
            "contact": "",
            "requirement": "发货到北京，联系人：张大山 13500001111。"
        },
        # 7. 名字和多个电话通过斜杠连接
        {
            "order_no": "C007",
            "contact": "",
            "requirement": "发货前沟通，明芬芬 027-86500928-8121 /18086086193 随货带走"
        },
        # 8. 名字紧接着多个电话用逗号连接
        {
            "order_no": "C008",
            "contact": "",
            "requirement": "请联系 李经理 13911112222, 13800003333"
        },
        # 9. 多个联系人分别出现
        {
            "order_no": "C009",
            "contact": "",
            "requirement": "收件人：张三 13800000001，如果不通请拨打 财务部李四，电话13900000002"
        },
        # 10. 名字直接跟着电话（较难的提取，不带前缀）
        {
            "order_no": "C010",
            "contact": "",
            "requirement": "务必交到门店 刘建国 13688889999 手里"
        },
        # 11. 干扰测试：防止把“有限公司”当成人名
        {
            "order_no": "C011",
            "contact": "",
            "requirement": "送到宏智仓储有限公司 13812345678"
        }
    ]
    
    for i, order in enumerate(cases, 1):
        print(f"--- 场景 {i} : [单号 {order['order_no']}] ---")
        print(f"   【原始 requirement】: {order['requirement']}")
        print(f"   【原始 contact】    : '{order['contact']}'")
        
        normalized_order = FieldNormalizer.normalize(order)
        
        print(f"   【修正后 contact】  : '{normalized_order.get('contact', '')}'")
        print("-" * 60)

if __name__ == "__main__":
    test_normalizer()
