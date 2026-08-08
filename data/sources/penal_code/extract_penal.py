"""Extract the Code Pénal Tunisien into code_penal.json."""

import sys
from pathlib import Path

# Add project root to sys.path to import pdf_extractor
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.pdf_extractor import build_articles, write_articles


def main() -> None:
    pdf_path = project_root / "data" / "sources" / "penal_code" / "Tunisia-Penal-Code-2012.pdf"
    output_json = project_root / "data" / "generated" / "code_penal.json"

    articles = build_articles(
        pdf_path,
        source="Code Penal Tunisien",
        law="code_penal",
        start_marker="LIVRE PREMIER",
        end_marker=r"^LIVRE\s+I\s*-\s*DISPOSITIONS"
    )
    write_articles(articles, output_json)
    print(f"Done! {len(articles)} chunks saved to {output_json}")


if __name__ == "__main__":
    main()
