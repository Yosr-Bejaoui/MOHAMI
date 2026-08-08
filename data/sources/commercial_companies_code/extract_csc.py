"""Extract the Code des Sociétés Commerciales into code_societes_commerciales.json."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.pdf_extractor import build_articles, write_articles

def main() -> None:
    pdf_path = project_root / "data" / "sources" / "commercial_companies_code" / "csc.pdf"
    output_json = project_root / "data" / "generated" / "code_societes_commerciales.json"

    articles = build_articles(
        pdf_path,
        source="Code des Sociétés Commerciales Tunisien",
        law="code_societes_commerciales",
        start_marker="LIVRE PREMIER",  # Fallback to Article 1 will happen if not found
    )
    write_articles(articles, output_json)
    print(f"Done! {len(articles)} chunks saved to {output_json}")

if __name__ == "__main__":
    main()
