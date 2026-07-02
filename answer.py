"""Generate Tunisian legal answers from retrieved articles using Gemini."""

from __future__ import annotations

import os
import sys

import google.generativeai as genai

from rag_utils import retrieve, get_system_prompt, _load_domain_config, is_gemini_available

GEMINI_MODEL = os.environ.get("MOHAMI_GEMINI_MODEL", "gemini-2.5-flash")


def _configure_genai() -> None:
    api_key = (
        os.environ.get("MOHAMI_GEMINI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or ""
    )
    if not api_key.strip():
        raise RuntimeError(
            "Missing Gemini API key. Set MOHAMI_GEMINI_API_KEY or GEMINI_API_KEY before running answer.py."
        )
    genai.configure(api_key=api_key.strip())


def build_context(hits: list[dict]) -> str:
    blocks: list[str] = []
    for index, hit in enumerate(hits, start=1):
        metadata = hit.get("metadata", {})
        article_number = metadata.get("article_number", "?")
        article_title = metadata.get("article_title", "Article")
        source = metadata.get("source", "")
        law = metadata.get("law", "")
        text = hit.get("text", "")
        blocks.append(
            f"Article {index}: {article_title} (article {article_number})\n"
            f"Source: {source}\n"
            f"Law: {law}\n"
            f"Texte:\n{text}"
        )
    return "\n\n".join(blocks)


def classify_domain(question: str) -> str:
    """Fast keyword-based domain classifier."""
    config = _load_domain_config()
    domains = list(config.get("domains", {}).keys())
    if "default" in domains:
        domains.remove("default")

    if not domains:
        return "default"

    question_lower = question.lower()
    best_domain = "default"
    max_score = 0

    for domain in domains:
        score = 0
        domain_config = config["domains"][domain]
        
        # Check synonyms
        synonyms = domain_config.get("synonyms", {})
        for key, terms in synonyms.items():
            for term in terms:
                if term in question_lower:
                    score += 1
                    
        # Check boost triggers
        for boost in domain_config.get("boosts", []):
            for trigger in boost.get("triggers", []):
                if trigger in question_lower:
                    score += 2
                    
        if score > max_score:
            max_score = score
            best_domain = domain

    return best_domain


def answer_question(question: str) -> tuple[str, list[dict], str]:
    domain = classify_domain(question)
    print(f"\n[Router] Detected Domain: {domain}")

    hits = retrieve(question, top_k=3, domain=domain)
    if not hits:
        return (
            "Je n'ai trouvé aucun article pertinent dans le corpus indexé.\n"
            "⚠️ Cette réponse est informative uniquement.\n"
            "Consultez un avocat pour votre situation spécifique.",
            [],
            domain
        )

    context = build_context(hits)
    user_prompt = (
        f"Question: {question}\n\n"
        "Articles fournis:\n"
        f"{context}\n\n"
        "Réponds uniquement avec les articles fournis. "
        "Cite les articles numéros dans la réponse. "
        "Si le texte ne suffit pas, dis-le clairement."
    )

    _configure_genai()
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=get_system_prompt(domain),
    )
    try:
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=900,
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        answer = (response.text or "").strip()
    except Exception as e:
        if "429" in str(e) or "Quota" in str(e):
            answer = "Désolé, le quota gratuit de l'API Google Gemini est épuisé. Veuillez réessayer plus tard ou vérifier votre clé API."
        else:
            answer = f"Erreur lors de la génération de la réponse: {str(e)}"
    if "⚠️ Cette réponse est informative uniquement." not in answer:
        answer = (
            f"{answer}\n\n"
            "⚠️ Cette réponse est informative uniquement.\n"
            "Consultez un avocat pour votre situation spécifique."
        ).strip()
    return answer, hits, domain


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python answer.py <question>")

    question = " ".join(sys.argv[1:]).strip()
    answer, _, _ = answer_question(question)
    print(answer)


if __name__ == "__main__":
    main()
