import re, os

print('=== main.py 拆单逻辑 ===')
with open('main.py', 'r', encoding='utf-8') as f:
    main = f.read()
idx = main.find('执行拆单新增指令')
print(main[idx:idx+600])
print()

print('=== cache_manager.py add_orders ===')
with open('utils/cache_manager.py', 'r', encoding='utf-8') as f:
    cm = f.read()
idx2 = cm.find('def add_orders')
end = cm.find('def save_pending', idx2)
if end == -1:
    end = cm.find('def load_pending', idx2)
print(cm[idx2:end])
print()

print('=== sync_orders.py 拆单相关 ===')
with open('sync_orders.py', 'r', encoding='utf-8') as f:
    so = f.read()
# 检查几个关键关键词
for kw in ['all_split', '"拆单"', "status = '拆单'", 'status = "拆单"']:
    count = so.count(kw)
    print(f'  {kw}: {count} 处')
print()
# 打印 yesterday_orders 写入逻辑部分
idx3 = so.find('8a. 写入昨日订单')
print(so[idx3:idx3+600])
