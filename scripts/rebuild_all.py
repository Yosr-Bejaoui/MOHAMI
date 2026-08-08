"""Regenerate JSON from PDF and rebuild the embedding index."""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    steps = []
    
    # Auto-discover and run all extract*.py scripts in data/sources subdirectories
    data_dir = PROJECT_ROOT / "data" / "sources"
    if data_dir.exists():
        for extract_script in data_dir.glob("**/extract*.py"):
            steps.append([sys.executable, str(extract_script)])
            
    steps.extend([
        [sys.executable, str(PROJECT_ROOT / "scripts" / "merge_corpus.py")],
        [sys.executable, str(PROJECT_ROOT / "scripts" / "index_corpus.py"), "--force"],
    ])
    for command in steps:
        print("Running:", " ".join(command))
        result = subprocess.run(command, cwd=str(PROJECT_ROOT))
        if result.returncode != 0:
            raise SystemExit(result.returncode)
            
    print("Rebuild complete.")
    
    stats_file = PROJECT_ROOT / "data" / "generated" / "dataset_stats.json"
    if stats_file.exists():
        with open(stats_file, "r", encoding="utf-8") as f:
            stats = json.load(f)
        print("\n=== Dataset Stats ===")
        print(f"Total Articles: {stats.get('total_articles')}")
        print(f"Total Characters: {stats.get('total_characters')}")
        print(f"Average Length: {stats.get('average_article_length')} chars")
        print("Articles per Law:")
        for law, count in stats.get("articles_per_law", {}).items():
            print(f"  - {law}: {count}")


if __name__ == "__main__":
    main()
