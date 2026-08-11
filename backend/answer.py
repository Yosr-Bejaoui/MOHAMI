"""Generate Tunisian legal answers from retrieved articles using Gemini."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai

from .rag_utils import retrieve, get_system_prompt, _load_domain_config, is_gemini_available

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

    confidence = min(max_score / 3.0, 1.0)
    if max_score == 0:
        confidence = 0.0
    return best_domain, confidence


def rewrite_query(question: str, domain: str) -> str:
    config = _load_domain_config()
    domains = config.get("domains", {})
    domain_config = domains.get(domain, domains.get("default", {}))
    
    synonyms_dict = domain_config.get("synonyms", {})
    expanded_terms = set()
    for key, terms in synonyms_dict.items():
        expanded_terms.update(terms)
        
    if expanded_terms:
        # Append unique synonyms to the question for semantic search enrichment
        return question + " " + " ".join(expanded_terms)
    
    return question

def generate_hyde(rewritten_query: str) -> str:
    _configure_genai()
    model = genai.GenerativeModel(GEMINI_MODEL)
    prompt = f"""Tu es un expert en droit tunisien.
Écris un court extrait d'article de loi tunisien (2-3 phrases)
qui répondrait directement à cette question :
{rewritten_query}
Réponds uniquement avec le texte de l'article hypothétique."""
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.3)
        )
        return (response.text or "").strip()
    except Exception:
        return ""

def answer_question(question: str) -> tuple[str, list[dict], str, str, str]:
    domain, confidence = classify_domain(question)
    print(f"\n[Router] Detected Domain: {domain} (Confidence: {confidence:.2f})")

    rewritten_query = rewrite_query(question, domain)
    print(f"Original: {question}")
    print(f"Rewritten: {rewritten_query}")

    hypothetical_article = ""
    if confidence < 0.5:
        print("[HyDE] Confidence below 0.5, generating hypothetical document...")
        hypothetical_article = generate_hyde(rewritten_query)
        combined = rewritten_query + " " + hypothetical_article
    else:
        print("[HyDE] High confidence, skipping HyDE to save API calls.")
        combined = rewritten_query

    hits = retrieve(combined, top_k=5, domain=domain)
    if not hits:
        return (
            "Je n'ai trouvé aucun article pertinent dans le corpus indexé.\n"
            "⚠️ Cette réponse est informative uniquement.\n"
            "Consultez un avocat pour votre situation spécifique.",
            [],
            domain,
            rewritten_query,
            hypothetical_article
        )

    context = build_context(hits)
    user_prompt = (
        f"Question: {question}\n\n"
        "Articles fournis:\n"
        f"{context}\n\n"
        "Réponds uniquement avec les articles fournis.\n"
        "Tu DOIS explicitement citer la loi et l'article pour chaque affirmation en utilisant EXACTEMENT le format: [Article X, Nom de la Loi].\n"
        "Par exemple: [Article 2, Code des Obligations et des Contrats Tunisien].\n"
        "Si le texte ne suffit pas pour répondre, dis-le clairement."
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
    return answer, hits, domain, rewritten_query, hypothetical_article


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python answer.py <question>")

    # Ensure stdout can handle UTF-8 characters on Windows
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    question = " ".join(sys.argv[1:]).strip()
    answer, _, _, _, _ = answer_question(question)
    print(answer)


if __name__ == "__main__":
    main()
