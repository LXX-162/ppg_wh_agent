import re
import sys

text1 = '发货地址:长春汽车经济技术开发区腾飞南路222号收货人赵丹，电话 15843095120'
text2 = '送货地址：郑州航空港经济综合实验区详符刘路以南、规划口案七街以东联系人张三'

addr_pattern = r'([\u4e00-\u9fa5]{2,20}(?:省|市|区|自治区|自治州|实验区)[\u4e00-\u9fa5A-Za-z0-9_ \-（）\(\)、「」、，]+(?:号|公司|集团|厂|仓库|基地|中心|车间|工业园|园区|区|东|南|西|北|侧)[）\)]?)'

with open("output.txt", "w", encoding="utf-8") as f:
    m1 = re.search(addr_pattern, text1)
    if m1: f.write("text1: " + m1.group(1) + "\n")
    
    m2 = re.search(addr_pattern, text2)
    if m2: f.write("text2: " + m2.group(1) + "\n")
