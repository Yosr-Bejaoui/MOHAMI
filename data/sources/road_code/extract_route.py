"""Extract the Code de la Route into code_route.json."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.pdf_extractor import build_articles, write_articles

def main() -> None:
    pdf_path = project_root / "data" / "sources" / "road_code" / "route.pdf"
    output_json = project_root / "data" / "generated" / "code_route.json"

    if not pdf_path.exists():
        print(f"SKIP: PDF not found at {pdf_path}")
        print("Please download the Code de la Route PDF manually and place it here.")
        return

    articles = build_articles(
        pdf_path,
        source="Code de la Route Tunisien",
        law="code_route",
        start_marker="LIVRE PREMIER",
    )
    write_articles(articles, output_json)
    print(f"Done! {len(articles)} chunks saved to {output_json}")

if __name__ == "__main__":
    main()
