"""Regenerate JSON from PDF and rebuild the embedding index."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    steps = []
    
    # Auto-discover and run all extract*.py scripts in mohami_data subdirectories
    data_dir = PROJECT_ROOT / "mohami_data"
    if data_dir.exists():
        for extract_script in data_dir.glob("**/extract*.py"):
            steps.append([sys.executable, str(extract_script)])
            
    steps.extend([
        [sys.executable, str(PROJECT_ROOT / "merge_corpus.py")],
        [sys.executable, str(PROJECT_ROOT / "index_corpus.py"), "--force"],
    ])
    for command in steps:
        print("Running:", " ".join(command))
        result = subprocess.run(command, cwd=str(PROJECT_ROOT))
        if result.returncode != 0:
            raise SystemExit(result.returncode)
    print("Rebuild complete.")


if __name__ == "__main__":
    main()
