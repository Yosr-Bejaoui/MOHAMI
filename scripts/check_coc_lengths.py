import json

with open("data/generated/code_coc.json", "r", encoding="utf-8") as f:
    data = json.load(f)

sorted_data = sorted(data, key=lambda x: len(x["text"]))

print("--- SHORTEST ---")
for a in sorted_data[:5]:
    print(f"{a['id']} length={len(a['text'])}")

print("--- LONGEST ---")
for a in sorted_data[-5:]:
    print(f"{a['id']} length={len(a['text'])}")
