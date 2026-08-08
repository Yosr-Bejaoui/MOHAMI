"""Extract the Code des Obligations et des Contrats (COC) into code_coc.json."""

import sys
from pathlib import Path

# Add project root to sys.path to import pdf_extractor
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.pdf_extractor import build_articles, write_articles


def main() -> None:
    pdf_path = project_root / "data" / "sources" / "civil_code" / "CODE COC.pdf"
    output_json = project_root / "data" / "generated" / "code_coc.json"

    articles = build_articles(
        pdf_path,
        source="Code des Obligations et des Contrats",
        law="code_coc",
        start_marker="LIVRE PREMIER",
        end_marker=None
    )
    write_articles(articles, output_json)
    print(f"Done! {len(articles)} chunks saved to {output_json}")


if __name__ == "__main__":
    main()
