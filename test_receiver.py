import logging
logging.basicConfig(level=logging.INFO)
from business.field_normalizer import FieldNormalizer

order = {
    'order_date': 'July 14, 2026', 
    'address': 'HUBEI HUAKAI~湖北华楷汽车零部件有限公司 湖北省孝感市孝南区东山头工业园区沦河二路88号', 
    'requirement': '华楷订单结单'
}

res = FieldNormalizer.normalize(order)
print(f"Date: {res['order_date']}, Receiver: {res.get('receiver')}")
