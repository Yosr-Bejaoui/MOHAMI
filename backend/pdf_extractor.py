import json
import re
import argparse
from pathlib import Path

from pypdf import PdfReader

ARTICLE_HEAD = r"(?:premier|1er|\d+(?:\s+(?:bis|ter|quater|quinquies|sexies))?)"
ARTICLE_PATTERN = re.compile(
    rf"^(?:Article|Art\.?)\s+{ARTICLE_HEAD}\b",
    re.IGNORECASE | re.MULTILINE,
)
INLINE_ARTICLE_PATTERN = re.compile(
    rf"(?:^|\n)\s*((?:Article|Art\.?)\s+{ARTICLE_HEAD})\s*",
    re.IGNORECASE,
)
LIVRE_PATTERN = re.compile(r"^LIVRE\s+(.+)$", re.IGNORECASE | re.MULTILINE)
TITRE_PATTERN = re.compile(r"^TITRE\s+(.+)$", re.IGNORECASE | re.MULTILINE)
CHAPITRE_PATTERN = re.compile(r"^CHAPITRE\s+(.+)$", re.IGNORECASE | re.MULTILINE)
TABLE_OF_CONTENTS = re.compile(r"TABLE\s+DE\s+MATIERES", re.IGNORECASE)
STRUCTURAL_TAIL = re.compile(
    r"\n\s*(?:CHAPITRE|LIVRE|TITRE|Section)\s+.+$",
    re.IGNORECASE | re.DOTALL,
)
MAX_CHUNK_CHARS = 1200




def extract_raw_text(pdf_path: str | Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


def clean_text(text: str) -> str:
    text = re.sub(
        r"Imprimerie\s+Officielle\s+de\s+la\s+R[eé]publique\s+Tunisienne\s*\n?\s*\d*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"Impeimerie\s+Officielle", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Imprimerie\s+Officielle", "", text, flags=re.IGNORECASE)
    text = re.sub(r"République\s+Tunisienne", "", text, flags=re.IGNORECASE)
    
    lines = []
    for line in text.split('\n'):
        line_stripped = line.strip()
        if line_stripped.isdigit():
            continue
        if len(line_stripped) > 0 and len(line_stripped) < 3:
            continue
        lines.append(line)
        
    text = '\n'.join(lines)
    
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _normalize_heading(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip(" .")


def _slug(value: str) -> str:
    value = value.lower()
    value = value.replace("premier", "1")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "unknown"


def _article_number(article_title: str) -> str:
    match = re.search(rf"({ARTICLE_HEAD})", article_title, re.IGNORECASE)
    return match.group(0).strip() if match else "unknown"


def _split_long_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars + 150:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return [text[:max_chars]]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        
        if current:
            chunks.append(current)
            
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
            
        start = 0
        while start < len(paragraph):
            end = start + max_chars
            if len(paragraph) - end < 150:
                end = len(paragraph)
            chunks.append(paragraph[start : end])
            start = end
        current = ""

    if current:
        if chunks and len(current) < 150:
            chunks[-1] = f"{chunks[-1]}\n\n{current}"
        else:
            chunks.append(current)
            
    return chunks


def _trim_to_code_body(text: str, start_marker: str = "LIVRE PREMIER", end_marker: str | None = None) -> str:
    start = text.find(start_marker)
    if start == -1:
        # Fallback to the first article if the specific marker is not found
        article_match = re.search(r"(?:Article|Art\.?)\s+(?:premier|1er|1\b)", text, re.IGNORECASE)
        if article_match:
            start = article_match.start()
        else:
            raise ValueError(f"Could not find the start marker '{start_marker}' or the first article in the PDF.")

    body = text[start:]
    if end_marker:
        end_match = re.search(end_marker, body, re.IGNORECASE | re.MULTILINE)
        if end_match:
            body = body[: end_match.start()].strip()

    table_match = TABLE_OF_CONTENTS.search(body)
    if table_match:
        body = body[: table_match.start()].strip()

    return body


def _strip_structural_noise(content: str) -> str:
    content = STRUCTURAL_TAIL.sub("", content).strip()
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def _split_inline_articles(primary_title: str, content: str) -> list[tuple[str, str]]:
    matches = list(INLINE_ARTICLE_PATTERN.finditer(content))
    if not matches:
        cleaned = _strip_structural_noise(content)
        return [(primary_title, cleaned)] if cleaned else []

    parts: list[tuple[str, str]] = []
    prefix = content[: matches[0].start()].strip()
    if prefix:
        cleaned = _strip_structural_noise(prefix)
        if cleaned:
            parts.append((primary_title, cleaned))

    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sub_content = _strip_structural_noise(content[start:end].strip())
        if sub_content:
            parts.append((title, sub_content))

    return parts


def _build_search_text(article_title: str, content: str, metadata: dict) -> str:
    keywords = " ".join(
        filter(
            None,
            [
                metadata.get("livre", ""),
                metadata.get("titre", ""),
                metadata.get("chapitre", ""),
                metadata.get("article_number", ""),
            ],
        )
    )
    return f"{article_title}\n{keywords}\n{content}"


def parse_articles(raw_text: str, source: str, law: str, start_marker: str = "LIVRE PREMIER", end_marker: str | None = None) -> list[dict]:
    body = _trim_to_code_body(raw_text, start_marker, end_marker)
    matches = list(ARTICLE_PATTERN.finditer(body))
    articles_db: list[dict] = []

    current_livre = "LIVRE PREMIER"
    current_titre = ""
    current_chapitre = ""

    for index, match in enumerate(matches):
        article_title = match.group(0).strip()
        start_idx = match.start()
        end_idx = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[start_idx:end_idx]

        if TABLE_OF_CONTENTS.search(section):
            continue

        between = body[matches[index - 1].start() : start_idx] if index > 0 else body[:start_idx]
        heading_zone = between[-800:] if len(between) > 800 else between
        for heading_match in LIVRE_PATTERN.finditer(heading_zone):
            current_livre = _normalize_heading(heading_match.group(1))
            current_titre = ""
            current_chapitre = ""
        for heading_match in TITRE_PATTERN.finditer(heading_zone):
            current_titre = _normalize_heading(heading_match.group(1))
        for heading_match in CHAPITRE_PATTERN.finditer(heading_zone):
            current_chapitre = _normalize_heading(heading_match.group(1))

        article_content = ARTICLE_PATTERN.sub("", section, count=1).strip()
        if len(article_content) < 15:
            continue

        sub_articles = _split_inline_articles(article_title, article_content)
        for sub_title, sub_content in sub_articles:
            if len(sub_content) < 15 or TABLE_OF_CONTENTS.search(sub_content):
                continue

            article_number = _article_number(sub_title)
            base_id = f"{_slug(law)}_{_slug(current_livre)}_art_{_slug(article_number)}"
            metadata = {
                "source": source,
                "law": law,
                "livre": current_livre,
                "titre": current_titre,
                "chapitre": current_chapitre,
                "article_title": sub_title,
                "article_number": article_number,
            }
            chunks = _split_long_text(sub_content)

            for part_index, chunk in enumerate(chunks):
                chunk_id = base_id if len(chunks) == 1 else f"{base_id}_p{part_index}"
                articles_db.append(
                    {
                        "id": chunk_id,
                        "text": f"{sub_title}\n{chunk}",
                        "search_text": _build_search_text(sub_title, chunk, metadata),
                        "metadata": {
                            **metadata,
                            "part": str(part_index),
                            "parts_total": str(len(chunks)),
                        },
                    }
                )

    return articles_db


def build_articles(pdf_path: Path, source: str, law: str, start_marker: str = "LIVRE PREMIER", end_marker: str | None = None) -> list[dict]:
    raw = extract_raw_text(pdf_path)
    cleaned = clean_text(raw)
    return parse_articles(cleaned, source=source, law=law, start_marker=start_marker, end_marker=end_marker)


def write_articles(articles: list[dict], output_json: Path) -> None:
    with open(output_json, "w", encoding="utf-8") as file:
        json.dump(articles, file, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Tunisian legal articles from a PDF.")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "sources" / "penal_code" / "Tunisia-Penal-Code-2012.pdf",
        help="Path to the source PDF.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "generated" / "code_penal.json",
        help="Where to write the extracted JSON.",
    )
    parser.add_argument(
        "--source",
        default="Code Penal Tunisien",
        help="Human-readable source name.",
    )
    parser.add_argument(
        "--law",
        default="code_penal",
        help="Stable law identifier stored in metadata.",
    )
    parser.add_argument(
        "--start-marker",
        default="LIVRE PREMIER",
        help="Text indicating the start of the legal body (e.g. 'LIVRE PREMIER', 'TITRE I').",
    )
    parser.add_argument(
        "--end-marker",
        default=None,
        help="Regex pattern indicating where to stop extracting (e.g. '^LIVRE I - DISPOSITIONS').",
    )
    args = parser.parse_args()

    articles = build_articles(
        args.pdf, 
        source=args.source, 
        law=args.law, 
        start_marker=args.start_marker,
        end_marker=args.end_marker
    )
    write_articles(articles, args.output)

    print(f"Done! {len(articles)} chunks saved to {args.output}")


if __name__ == "__main__":
    main()
