"""Merge all code_*.json files into corpus.json."""

import json
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent
    sources = list(project_root.glob("code_*.json"))
    if not sources:
        print("No source files found matching code_*.json")
        return
    corpus_path = project_root / "corpus.json"

    corpus: list[dict] = []
    for source_path in sources:
        with open(source_path, "r", encoding="utf-8") as file:
            corpus.extend(json.load(file))

    with open(corpus_path, "w", encoding="utf-8") as file:
        json.dump(corpus, file, ensure_ascii=False, indent=2)

    print(f"Merged {sum(1 for _ in corpus)} chunks into {corpus_path}")


if __name__ == "__main__":
    main()