from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_PATH = PROJECT_ROOT / "corpus.json"
EMBEDDINGS_CACHE = PROJECT_ROOT / "embeddings_cache.npz"
DOMAIN_CONFIG_PATH = PROJECT_ROOT / "domain_config.json"
EMBEDDING_MODELS = [
    "intfloat/multilingual-e5-base",
    "paraphrase-multilingual-MiniLM-L12-v2",
]
BATCH_SIZE = 8
CACHE_VERSION = "2"
ENCODER_STARTUP_TIMEOUT_SECONDS = 120
RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
RERANKER_CANDIDATES = 10
GEMINI_BASE_URL = os.environ.get(
    "MOHAMI_GEMINI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta",
)
GEMINI_API_KEY = os.environ.get(
    "MOHAMI_GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", "")
)
GEMINI_MODEL = os.environ.get("MOHAMI_GEMINI_MODEL", "gemini-2.5-flash")

# Backward-compatible aliases for any older notebook cells or scripts.
GROQ_BASE_URL = GEMINI_BASE_URL
GROQ_API_KEY = GEMINI_API_KEY
GROQ_MODEL = GEMINI_MODEL
OLLAMA_URL = GEMINI_BASE_URL
OLLAMA_MODEL = GEMINI_MODEL

_ENCODER_PROCESS: subprocess.Popen[str] | None = None
_ENCODER_MODEL_NAME: str | None = None
_BM25_CACHE: dict | None = None
_DOMAIN_CONFIG: dict | None = None
_RERANKER = None

ARTICLE_HEAD = r"(?:premier|1er|\d+(?:\s+(?:bis|ter|quater|quinquies|sexies))?)"
ARTICLE_QUERY_PATTERN = re.compile(rf"article\s+({ARTICLE_HEAD})", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"[\wàâäéèêëïîôùûüç]+", re.IGNORECASE)


def _load_domain_config() -> dict:
    """Load domain configuration from domain_config.json."""
    global _DOMAIN_CONFIG
    if _DOMAIN_CONFIG is not None:
        return _DOMAIN_CONFIG
    if DOMAIN_CONFIG_PATH.exists():
        with open(DOMAIN_CONFIG_PATH, "r", encoding="utf-8") as f:
            _DOMAIN_CONFIG = json.load(f)
    else:
        _DOMAIN_CONFIG = {}
    return _DOMAIN_CONFIG


def _get_domain_config(domain: str) -> dict:
    config = _load_domain_config()
    domains = config.get("domains", {})
    return domains.get(domain, domains.get("default", {}))


def _get_synonyms(domain: str = "default") -> dict[str, list[str]]:
    """Get legal synonyms from domain config."""
    return _get_domain_config(domain).get("synonyms", {})


def _get_corpus_label(domain: str = "default") -> str:
    """Get the human-readable corpus label for user-facing text."""
    return _get_domain_config(domain).get("corpus_label", "la législation tunisienne indexée")


def get_system_prompt(domain: str = "default") -> str:
    """Get the system prompt for the LLM from domain config."""
    config = _get_domain_config(domain)
    return config.get("system_prompt",
        "You are a Tunisian legal assistant. "
        "Answer ONLY based on the provided legal articles. "
        "Use simple clear French, no legal jargon. "
        "Cite the article number in your answer."
    )


FRENCH_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou", "en",
    "au", "aux", "pour", "par", "sur", "dans", "que", "qui", "quoi", "est",
    "sont", "avec", "sans", "ce", "cette", "ces", "son", "sa", "ses", "leur",
    "leurs", "il", "elle", "on", "nous", "vous", "ils", "elles", "ne", "pas",
    "plus", "moins", "tres", "très", "a", "à", "comment", "quelle", "quel",
    "quelles", "quels", "selon", "code", "dit", "loi", "peine",
}


def configure_windows_runtime() -> None:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def load_articles(path: Path | None = None) -> list[dict]:
    data_path = path or DATA_PATH
    with open(data_path, "r", encoding="utf-8") as file:
        return json.load(file)


def is_index_ready() -> bool:
    if not EMBEDDINGS_CACHE.exists() or EMBEDDINGS_CACHE.stat().st_size == 0:
        return False
    try:
        cache = np.load(EMBEDDINGS_CACHE, allow_pickle=True)
        version = str(cache["cache_version"]) if "cache_version" in cache else ""
        return (
            "embeddings" in cache
            and len(cache["embeddings"]) > 0
            and "search_texts" in cache
            and version == CACHE_VERSION
        )
    except Exception:
        return False


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _expand_query_tokens(tokens: list[str], domain: str = "default") -> list[str]:
    expanded = list(tokens)
    for token in tokens:
        for key, synonyms in _get_synonyms(domain).items():
            if token == key or token in synonyms:
                expanded.extend(synonyms)
    return list(dict.fromkeys(expanded))


def tokenize(text: str, expand: bool = False) -> list[str]:
    tokens = TOKEN_PATTERN.findall(_normalize_text(text))
    filtered = [token for token in tokens if len(token) > 2 and token not in FRENCH_STOPWORDS]
    return _expand_query_tokens(filtered) if expand else filtered


def _is_e5_model(model_name: str) -> bool:
    return "e5" in model_name.lower()


def _load_embedding_model():
    configure_windows_runtime()
    from sentence_transformers import SentenceTransformer

    errors: list[str] = []
    for model_name in EMBEDDING_MODELS:
        try:
            model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
            return model, model_name
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")
    raise RuntimeError("No embedding model available locally. " + " | ".join(errors))


def get_embedding_model():
    model, _ = _load_embedding_model()
    return model


def _prepare_texts_for_model(model_name: str, texts: list[str], is_query: bool) -> list[str]:
    if not _is_e5_model(model_name):
        return texts
    prefix = "query: " if is_query else "passage: "
    return [prefix + text for text in texts]


def encode_texts(model, model_name: str, texts: list[str], is_query: bool = False) -> list[list[float]]:
    prepared = _prepare_texts_for_model(model_name, texts, is_query)
    vectors = model.encode(
        prepared,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return vectors.tolist()


def save_embedding_cache(articles: list[dict], embeddings: list[list[float]], model_name: str) -> None:
    ids = np.array([article["id"] for article in articles], dtype=object)
    texts = np.array([article["text"] for article in articles], dtype=object)
    search_texts = np.array(
        [article.get("search_text", article["text"]) for article in articles],
        dtype=object,
    )
    metadatas = np.array(
        [json.dumps(article["metadata"], ensure_ascii=False) for article in articles],
        dtype=object,
    )
    vectors = np.array(embeddings, dtype=np.float32)
    np.savez_compressed(
        EMBEDDINGS_CACHE,
        ids=ids,
        texts=texts,
        search_texts=search_texts,
        metadatas=metadatas,
        embeddings=vectors,
        model_name=np.array(model_name),
        cache_version=np.array(CACHE_VERSION),
    )
    global _BM25_CACHE
    _BM25_CACHE = None


def load_embedding_cache() -> dict[str, np.ndarray]:
    if not is_index_ready():
        raise FileNotFoundError(
            f"Embedding cache not found at {EMBEDDINGS_CACHE}. Run: python index_corpus.py --force"
        )
    return np.load(EMBEDDINGS_CACHE, allow_pickle=True)


def _cache_model_name(cache: dict[str, np.ndarray]) -> str:
    if "model_name" not in cache:
        raise RuntimeError(
            "Embedding cache is missing model_name. Rebuild the index with: python index_corpus.py --force"
        )
    return str(cache["model_name"]).strip()


def index_articles(articles: list[dict] | None = None, reset: bool = True) -> int:
    articles = articles or load_articles()
    if reset and EMBEDDINGS_CACHE.exists():
        EMBEDDINGS_CACHE.unlink()

    model, model_name = _load_embedding_model()
    search_texts = [article.get("search_text", article["text"]) for article in articles]
    all_embeddings: list[list[float]] = []

    for start in range(0, len(articles), BATCH_SIZE):
        batch_texts = search_texts[start : start + BATCH_SIZE]
        all_embeddings.extend(encode_texts(model, model_name, batch_texts, is_query=False))

    save_embedding_cache(articles, all_embeddings, model_name)
    return len(articles)


def run_index_subprocess(force: bool = False) -> str:
    if is_index_ready() and not force:
        return f"Index already exists ({EMBEDDINGS_CACHE.name})."

    command = [sys.executable, str(PROJECT_ROOT / "index_corpus.py")]
    if force:
        command.append("--force")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Indexing failed").strip())
    return output or "Indexing completed."


def ensure_index(force: bool = False) -> str:
    return run_index_subprocess(force=force)


def _readline_with_timeout(stream, timeout_seconds: float) -> str | None:
    line_queue: queue.Queue[str | None] = queue.Queue(maxsize=1)

    def _reader() -> None:
        try:
            line_queue.put(stream.readline())
        except Exception:
            line_queue.put(None)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    try:
        return line_queue.get(timeout=timeout_seconds)
    except queue.Empty:
        return None


def _start_encoder_process(timeout_seconds: int = ENCODER_STARTUP_TIMEOUT_SECONDS) -> subprocess.Popen[str]:
    global _ENCODER_PROCESS
    global _ENCODER_MODEL_NAME
    if _ENCODER_PROCESS is not None and _ENCODER_PROCESS.poll() is None:
        return _ENCODER_PROCESS

    process = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "encode_query_server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    assert process.stderr is not None
    startup_logs: list[str] = []
    deadline = time.time() + timeout_seconds
    ready_line = ""
    while time.time() < deadline:
        remaining = max(0.1, deadline - time.time())
        line = _readline_with_timeout(process.stderr, remaining)
        if line is None:
            continue

        stripped = line.strip()
        if not stripped:
            if process.poll() is not None:
                break
            continue

        if stripped.startswith("encoder-ready:"):
            ready_line = stripped
            break

        startup_logs.append(stripped)
        if process.poll() is not None:
            break

    if not ready_line:
        process.kill()
        process.wait(timeout=5)
        extra = " | ".join(startup_logs[-5:]).strip()
        raise RuntimeError(
            "Encoder failed to start within "
            f"{timeout_seconds}s: {extra or 'no ready signal'}"
        )

    _ENCODER_MODEL_NAME = ready_line.split(":", 1)[1].strip() or None

    _ENCODER_PROCESS = process
    return process


def shutdown_encoder_process() -> None:
    global _ENCODER_PROCESS
    global _ENCODER_MODEL_NAME
    if _ENCODER_PROCESS is None or _ENCODER_PROCESS.poll() is not None:
        _ENCODER_PROCESS = None
        _ENCODER_MODEL_NAME = None
        return

    if _ENCODER_PROCESS.stdin is not None:
        _ENCODER_PROCESS.stdin.write("__quit__\n")
        _ENCODER_PROCESS.stdin.flush()
    try:
        _ENCODER_PROCESS.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _ENCODER_PROCESS.kill()
        _ENCODER_PROCESS.wait(timeout=5)
    _ENCODER_PROCESS = None
    _ENCODER_MODEL_NAME = None


def _ensure_cache_encoder_consistency(cache: dict[str, np.ndarray]) -> None:
    _start_encoder_process()
    cache_model_name = _cache_model_name(cache)
    encoder_model_name = (_ENCODER_MODEL_NAME or "").strip()

    if cache_model_name != encoder_model_name:
        shutdown_encoder_process()
        raise RuntimeError(
            "Embedding cache/model mismatch: "
            f"cache uses '{cache_model_name}' but query encoder loaded '{encoder_model_name}'. "
            "Run: python index_corpus.py --force"
        )


def encode_query_via_subprocess(question: str) -> np.ndarray:
    process = _start_encoder_process()
    assert process.stdin is not None
    assert process.stdout is not None

    process.stdin.write(question.replace("\n", " ").strip() + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        stderr = (process.stderr.read() if process.stderr else "") or "No encoder output"
        shutdown_encoder_process()
        raise RuntimeError(stderr.strip())

    vector = json.loads(line.strip())
    return np.array(vector, dtype=np.float32)


def _extract_article_refs(question: str) -> set[str]:
    refs = set()
    for match in ARTICLE_QUERY_PATTERN.finditer(question):
        refs.add(match.group(1).lower().strip())
    if re.search(r"\barticle\s+premier\b", question, re.I):
        refs.add("premier")
    return refs


def _article_match_score(metadata: dict, article_refs: set[str], query_tokens: list[str]) -> float:
    if not article_refs:
        return 0.0

    number = str(metadata.get("article_number", "")).lower().strip()
    title = str(metadata.get("article_title", "")).lower().strip()
    if number in article_refs or any(ref in title for ref in article_refs):
        return 1.0
    return 0.0


def _build_bm25(corpus_tokens: list[list[str]]) -> dict:
    doc_count = len(corpus_tokens)
    doc_freq: Counter[str] = Counter()
    tokenized_docs: list[Counter[str]] = []

    for tokens in corpus_tokens:
        counts = Counter(tokens)
        tokenized_docs.append(counts)
        doc_freq.update(counts.keys())

    avg_doc_len = sum(sum(counter.values()) for counter in tokenized_docs) / max(doc_count, 1)
    return {
        "docs": tokenized_docs,
        "doc_freq": doc_freq,
        "doc_count": doc_count,
        "avg_doc_len": avg_doc_len,
    }


def _bm25_scores(query_tokens: list[str], bm25: dict, k1: float = 1.5, b: float = 0.75) -> np.ndarray:
    scores = np.zeros(bm25["doc_count"], dtype=np.float32)
    if not query_tokens:
        return scores

    query_counts = Counter(query_tokens)
    for term, q_freq in query_counts.items():
        if term not in bm25["doc_freq"]:
            continue
        df = bm25["doc_freq"][term]
        idf = math.log(1 + (bm25["doc_count"] - df + 0.5) / (df + 0.5))
        for doc_index, doc_counts in enumerate(bm25["docs"]):
            tf = doc_counts.get(term, 0)
            if tf == 0:
                continue
            doc_len = sum(doc_counts.values())
            denom = tf + k1 * (1 - b + b * doc_len / bm25["avg_doc_len"])
            scores[doc_index] += idf * (tf * (k1 + 1)) / denom * q_freq
    return scores


def _keyword_overlap(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    query_set = set(query_tokens)
    doc_set = set(doc_tokens)
    return len(query_set & doc_set) / len(query_set)


def _normalize_scores(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    min_score = float(scores.min())
    max_score = float(scores.max())
    if math.isclose(min_score, max_score):
        return np.zeros_like(scores)
    return (scores - min_score) / (max_score - min_score)


def _get_bm25_cache(cache: dict[str, np.ndarray]) -> dict:
    global _BM25_CACHE
    if _BM25_CACHE is not None:
        return _BM25_CACHE

    search_texts = cache["search_texts"] if "search_texts" in cache else cache["texts"]
    corpus_tokens = [tokenize(str(text)) for text in search_texts]
    _BM25_CACHE = _build_bm25(corpus_tokens)
    _BM25_CACHE["corpus_tokens"] = corpus_tokens
    return _BM25_CACHE


def _normalize_article_number(value: str) -> str:
    return _normalize_text(str(value)).replace("  ", " ").strip()


def _article_matches_metadata(metadata: dict, law: str, article_number: str) -> bool:
    metadata_law = _normalize_article_number(metadata.get("law", ""))
    metadata_number = _normalize_article_number(metadata.get("article_number", ""))
    return metadata_law == _normalize_article_number(law) and metadata_number == _normalize_article_number(article_number)


def _find_best_article_index(cache: dict[str, np.ndarray], law: str, article_number: str) -> int | None:
    for index, metadata_json in enumerate(cache["metadatas"]):
        metadata = json.loads(str(metadata_json))
        if _article_matches_metadata(metadata, law, article_number):
            return index
    return None


def _get_matched_boosts(question: str, domain: str = "default") -> list[dict]:
    """Return boost rules from domain_config.json whose triggers match the question."""
    config = _get_domain_config(domain)
    normalized = _normalize_text(question)
    matched: list[dict] = []
    for boost in config.get("boosts", []):
        if any(trigger in normalized for trigger in boost.get("triggers", [])):
            matched.append(boost)
    return matched


def _dedupe_hits_by_article(hits: list[dict]) -> list[dict]:
    best_hits: dict[tuple[str, str], dict] = {}
    for hit in hits:
        metadata = hit["metadata"]
        key = (
            str(metadata.get("law", "")),
            str(metadata.get("article_number", "")),
        )
        existing = best_hits.get(key)
        if existing is None or hit.get("rerank_score", float("-inf")) > existing.get("rerank_score", float("-inf")):
            best_hits[key] = hit
    return sorted(best_hits.values(), key=lambda item: item.get("rerank_score", float("-inf")), reverse=True)


def _load_reranker():
    global _RERANKER
    if _RERANKER is not None:
        return _RERANKER

    configure_windows_runtime()
    from sentence_transformers import CrossEncoder

    _RERANKER = CrossEncoder(RERANKER_MODEL, device="cpu")
    return _RERANKER


def _rerank_hits(question: str, candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []

    reranker = _load_reranker()
    pairs = [(question, hit["text"]) for hit in candidates]
    rerank_scores = reranker.predict(pairs, batch_size=BATCH_SIZE, show_progress_bar=False)

    reranked: list[dict] = []
    for hit, rerank_score in zip(candidates, rerank_scores):
        enriched = dict(hit)
        enriched["rerank_score"] = float(rerank_score)
        reranked.append(enriched)

    reranked.sort(key=lambda item: item["rerank_score"], reverse=True)
    return reranked


def retrieve(question: str, top_k: int = 3, domain: str = "default") -> list[dict]:
    cache = load_embedding_cache()
    _ensure_cache_encoder_consistency(cache)
    bm25_cache = _get_bm25_cache(cache)

    query_vector = encode_query_via_subprocess(question)
    embeddings = cache["embeddings"]
    if embeddings.ndim != 2 or query_vector.shape[0] != embeddings.shape[1]:
        raise RuntimeError(
            "Embedding dimension mismatch between cache and query encoder. "
            "Run: python index_corpus.py --force"
        )
    semantic_scores = embeddings @ query_vector
    query_tokens = tokenize(question, expand=True)
    bm25_scores = _bm25_scores(query_tokens, bm25_cache)
    article_refs = _extract_article_refs(question)
    article_scores = np.zeros(len(semantic_scores), dtype=np.float32)
    keyword_scores = np.zeros(len(semantic_scores), dtype=np.float32)

    domain_data = _get_domain_config(domain)
    allowed_laws = domain_data.get("laws", [])

    for index, metadata_json in enumerate(cache["metadatas"]):
        metadata = json.loads(str(metadata_json))
        article_scores[index] = _article_match_score(metadata, article_refs, query_tokens)
        keyword_scores[index] = _keyword_overlap(query_tokens, bm25_cache["corpus_tokens"][index])

    norm_semantic = _normalize_scores(semantic_scores)
    norm_bm25 = _normalize_scores(bm25_scores)

    if article_refs:
        combined = 0.25 * norm_semantic + 0.20 * norm_bm25 + 0.15 * keyword_scores + 0.40 * article_scores
    else:
        combined = 0.50 * norm_semantic + 0.35 * norm_bm25 + 0.15 * keyword_scores

    # Hard-filter disallowed laws mathematically
    if allowed_laws:
        for index, metadata_json in enumerate(cache["metadatas"]):
            metadata = json.loads(str(metadata_json))
            if metadata.get("law") not in allowed_laws:
                combined[index] = -np.inf

    candidate_count = min(len(combined), max(top_k, RERANKER_CANDIDATES))
    candidate_indices = np.argsort(combined)[::-1][:candidate_count]
    candidates: list[dict] = []
    for index in candidate_indices:
        metadata = json.loads(str(cache["metadatas"][index]))
        candidates.append(
            {
                "id": str(cache["ids"][index]),
                "text": str(cache["texts"][index]),
                "metadata": metadata,
                "score": float(combined[index]),
                "semantic": float(norm_semantic[index]),
                "bm25": float(norm_bm25[index]),
            }
        )

    forced_candidates: list[dict] = []
    matched_boosts = _get_matched_boosts(question, domain)
    for boost in matched_boosts:
        for article_number in boost.get("articles", []):
            article_index = _find_best_article_index(cache, boost["law"], article_number)
            if article_index is None:
                continue
            metadata = json.loads(str(cache["metadatas"][article_index]))
            forced_candidates.append(
                {
                    "id": str(cache["ids"][article_index]),
                    "text": str(cache["texts"][article_index]),
                    "metadata": metadata,
                    "score": float(combined[article_index]),
                    "semantic": float(norm_semantic[article_index]),
                    "bm25": float(norm_bm25[article_index]),
                    "forced": True,
                }
            )

    candidates.extend(forced_candidates)

    reranked_hits = _rerank_hits(question, candidates)
    reranked_hits = _dedupe_hits_by_article(reranked_hits)

    if matched_boosts:
        forced_order: list[tuple[str, str]] = []
        for boost in matched_boosts:
            for article_number in boost.get("articles", []):
                forced_order.append((boost["law"], article_number))
        ordered_hits: list[dict] = []
        used_keys: set[tuple[str, str]] = set()
        for law, article_number in forced_order:
            for hit in reranked_hits:
                metadata = hit["metadata"]
                key = (str(metadata.get("law", "")), str(metadata.get("article_number", "")))
                if key == (law, article_number) and key not in used_keys:
                    ordered_hits.append(hit)
                    used_keys.add(key)
                    break
        for hit in reranked_hits:
            metadata = hit["metadata"]
            key = (str(metadata.get("law", "")), str(metadata.get("article_number", "")))
            if key not in used_keys:
                ordered_hits.append(hit)
                used_keys.add(key)
            if len(ordered_hits) >= top_k:
                break
        return ordered_hits[:top_k]

    return reranked_hits[:top_k]


def is_gemini_available() -> bool:
    if not GEMINI_API_KEY.strip():
        return False
    try:
        request = urllib.request.Request(
            f"{GEMINI_BASE_URL}/models?key={GEMINI_API_KEY}",
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


# Backward-compatible aliases
def is_groq_available() -> bool:
    return is_gemini_available()


def is_ollama_available() -> bool:
    return is_gemini_available()


def summarize_with_llm(question: str, hits: list[dict], domain: str = "default") -> str | None:
    if not hits or not is_gemini_available():
        return None

    context_blocks = []
    for hit in hits[:4]:
        metadata = hit["metadata"]
        context_blocks.append(
            f"- {metadata.get('article_title', 'Article')} "
            f"(Livre {metadata.get('livre', '')}, chapitre {metadata.get('chapitre', '')})\n"
            f"{hit['text']}"
        )

    system_instruction = (
        "Tu es un assistant juridique tunisien. Réponds en français clair et accessible. "
        "Utilise uniquement les articles fournis ci-dessous et cite leurs numéros."
    )

    user_prompt = (
        "Tu es un assistant juridique tunisien. Réponds en français clair et accessible.\n"
        "Utilise UNIQUEMENT les articles fournis ci-dessous. Cite les numéros d'articles.\n"
        "Si les textes ne suffisent pas, dis-le clairement.\n"
        "Rappelle que ce n'est pas un avis juridique officiel.\n\n"
        f"Question: {question}\n\n"
        f"Articles de {_get_corpus_label(domain)}:\n"
        + "\n\n".join(context_blocks)
        + "\n\nRéponse structurée:\n"
        "1) Ce que dit la loi\n"
        "2) Peines applicables (si mentionnées)\n"
        "3) Articles cités\n"
        "4) Mise en garde"
    )

    payload = json.dumps(
        {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 700,
            },
        }
    ).encode("utf-8")

    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return None
            return str(parts[0].get("text", "")).strip() or None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def format_legal_answer(question: str, hits: list[dict], use_llm: bool = True, domain: str = "default") -> str:
    corpus_label = _get_corpus_label(domain)
    if not hits:
        return (
            f"Je n'ai pas trouvé d'article pertinent dans {corpus_label}. "
            "Reformulez votre question ou consultez un avocat."
        )

    llm_answer = summarize_with_llm(question, hits) if use_llm else None
    lines = [
        f"Avertissement : cette réponse est une aide informative basée sur {corpus_label}. "
        "Elle ne remplace pas un avocat.",
        "",
        f"Question : {question}",
    ]

    if llm_answer:
        lines.extend(["", "Réponse :", llm_answer, "", "Sources :"])
    else:
        lines.extend(["", "Articles pertinents :"])

    for rank, hit in enumerate(hits, start=1):
        metadata = hit["metadata"]
        citation = (
            f"{metadata.get('article_title', 'Article')} "
            f"(Livre {metadata.get('livre', '')}"
            f"{', ch. ' + metadata.get('chapitre', '') if metadata.get('chapitre') else ''})"
        ).strip()
        lines.extend(
            [
                "",
                f"{rank}. {citation} [score={hit['score']:.2f}]",
                hit["text"],
            ]
        )

    if not llm_answer and use_llm:
        lines.extend(
            [
                "",
                "Astuce : définissez MOHAMI_GEMINI_API_KEY et MOHAMI_GEMINI_MODEL "
                "pour obtenir une réponse rédigée en français simple.",
            ]
        )

    lines.extend(
        [
            "",
            "Pour une situation personnelle, consultez un avocat inscrit au barreau tunisien.",
        ]
    )
    return "\n".join(lines)
