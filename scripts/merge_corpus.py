"""Merge all code_*.json files into corpus.json and generate a professional dataset."""

import csv
import json
import datetime
from pathlib import Path

LAW_NAMES = {
    "code_penal": "Code Pénal Tunisien",
    "code_procedure_penale": "Code de Procédure Pénale Tunisien",
    "code_travail": "Code du Travail Tunisien",
    "code_statut_personnel": "Code du Statut Personnel Tunisien",
    "code_coc": "Code des Obligations et des Contrats Tunisien",
    "code_commercial": "Code de Commerce Tunisien",
    "code_droits_reels": "Code des Droits Réels Tunisien",
    "code_procedure_civile_commerciale": "Code de Procédure Civile et Commerciale Tunisien",
    "constitution_2022": "Constitution de la République Tunisienne (2022)",
    "loi_violences_femmes": "Loi Organique sur l'élimination de la violence à l'égard des femmes (2017)",
    "loi_protection_donnees": "Loi Organique sur la protection des données à caractère personnel (2004)",
    "code_route": "Code de la Route Tunisien",
    "loi_antiterrorisme": "Loi relative à la lutte contre le terrorisme et le blanchiment d'argent (2015)",
    "loi_stupefiants": "Loi relative aux stupéfiants et aux substances psychotropes",
    "code_nationalite": "Code de la Nationalité Tunisienne",
    "code_securite_sociale": "Code de la Sécurité Sociale Tunisien",
    "code_societes_commerciales": "Code des Sociétés Commerciales Tunisien",
    "code_fiscal": "Code des Droits et Procédures Fiscaux Tunisien (2025)"
}

def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data" / "generated"
    sources = list(data_dir.glob("code_*.json"))
    if not sources:
        print("No source files found matching code_*.json")
        return

    # Output paths
    corpus_path = data_dir / "corpus.json"
    dataset_csv = data_dir / "tunisia_legal_dataset.csv"
    stats_json = data_dir / "dataset_stats.json"

    corpus: list[dict] = []
    for source_path in sources:
        with open(source_path, "r", encoding="utf-8") as file:
            corpus.extend(json.load(file))

    # Write merged JSON
    with open(corpus_path, "w", encoding="utf-8") as file:
        json.dump(corpus, file, ensure_ascii=False, indent=2)

    # Prepare stats
    total_articles = len(corpus)
    total_characters = 0
    articles_per_law: dict[str, int] = {}
    extraction_date = str(datetime.date.today())

    # Write full dataset CSV
    with open(dataset_csv, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            "id", "law_code", "law_name", "article_number", "article_title",
            "livre", "titre", "chapitre", "text", "text_length",
            "source_pdf", "extraction_date"
        ])
        
        for article in corpus:
            meta = article.get("metadata", {})
            law_code = meta.get("law", "")
            law_name = LAW_NAMES.get(law_code, law_code)
            text = article.get("text", "")
            text_len = len(text)
            
            # Update stats
            total_characters += text_len
            articles_per_law[law_name] = articles_per_law.get(law_name, 0) + 1
            
            writer.writerow([
                article.get("id", ""),
                law_code,
                law_name,
                meta.get("article_number", ""),
                meta.get("article_title", ""),
                meta.get("livre", ""),
                meta.get("titre", ""),
                meta.get("chapitre", ""),
                text,
                text_len,
                meta.get("source", ""),
                extraction_date
            ])

    # Save stats
    avg_length = round(total_characters / total_articles, 2) if total_articles > 0 else 0
    stats = {
        "total_articles": total_articles,
        "articles_per_law": articles_per_law,
        "average_article_length": avg_length,
        "total_characters": total_characters,
        "extraction_date": extraction_date
    }
    with open(stats_json, "w", encoding="utf-8") as file:
        json.dump(stats, file, ensure_ascii=False, indent=2)

    print(f"Merged {len(corpus)} chunks into {corpus_path}")
    print(f"Saved dataset CSV to {dataset_csv}")
    print(f"Saved stats JSON to {stats_json}")


if __name__ == "__main__":
    main()