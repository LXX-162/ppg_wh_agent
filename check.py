import json
with open("output/test_7_14_orders.json", "r", encoding="utf-8") as f:
    data = json.load(f)
for o in data:
    if o["order_no"] in ["11966184", "11966809", "11966312", "11966558", "11966552"]:
        print(f"[{o['order_no']}]")
        print(f"Address: {o['address']}")
        print(f"Contact: {o['contact']}")
        print("-" * 20)
