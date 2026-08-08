"""Extract the Code du Statut Personnel into code_statut_personnel.json."""

import sys
from pathlib import Path

# Add project root to sys.path to import pdf_extractor
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.pdf_extractor import build_articles, write_articles


def main() -> None:
    pdf_path = project_root / "data" / "sources" / "personal_status_code" / "code du statut personnel_fr.pdf"
    output_json = project_root / "data" / "generated" / "code_statut_personnel.json"

    articles = build_articles(
        pdf_path,
        source="Code du Statut Personnel Tunisien",
        law="code_statut_personnel",
    )
    write_articles(articles, output_json)
    print(f"Done! {len(articles)} chunks saved to {output_json}")


if __name__ == "__main__":
    main()
