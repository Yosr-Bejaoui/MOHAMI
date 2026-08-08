"""Debug: Check LIVRE PREMIER articles in COC corpus."""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
data_path = PROJECT_ROOT / "data" / "generated" / "corpus.json"
with open(data_path, "r", encoding="utf-8") as f:
    data = json.load(f)
coc = [a for a in data if a["metadata"]["law"] == "code_coc"]

# Show first 30 COC articles by index order 
print(f"Total COC chunks: {len(coc)}")
print("\n=== First 30 COC articles ===")
for i, a in enumerate(coc[:30]):
    livre = a["metadata"].get("livre", "?")
    art = a["metadata"].get("article_number", "?")
    print(f"{i}: ID={a['id']}  livre={livre}  art={art}  text={a['text'][:100]}")

# Check all unique livre values
livres = set(a["metadata"].get("livre", "?") for a in coc)
print(f"\n=== Unique LIVRE values ({len(livres)}) ===")
for l in sorted(livres):
    count = sum(1 for a in coc if a["metadata"].get("livre", "") == l)
    print(f"  {l}: {count} chunks")
