"""Extract the Code de Procédure Pénale Tunisien into code_cpp.json."""

import sys
from pathlib import Path

# Add project root to sys.path to import pdf_extractor
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.pdf_extractor import build_articles, write_articles


def main() -> None:
    pdf_path = project_root / "data" / "sources" / "penal_code" / "CODE DES PROCEDURES PENALES.pdf"
    output_json = project_root / "data" / "generated" / "code_cpp.json"

    articles = build_articles(
        pdf_path,
        source="Code de Procédure Pénale Tunisien",
        law="code_procedure_penale",
    )
    write_articles(articles, output_json)
    print(f"Done! {len(articles)} chunks saved to {output_json}")


if __name__ == "__main__":
    main()