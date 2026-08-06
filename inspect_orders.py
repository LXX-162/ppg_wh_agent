import json

with open('output/cache/pending_orders.json', encoding='utf-8') as f:
    d = json.load(f)

print(f"Total orders: {len(d)}")
print("=" * 100)
for k, v in d.items():
    print(k, "|", v.get('address', ''), "| contact:", v.get('contact', ''))
