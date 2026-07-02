# MOHAMI - AI Legal RAG Assistant

MOHAMI is an advanced Retrieval-Augmented Generation (RAG) assistant designed for Tunisian Law. It extracts legal text from PDFs, indexes them semantically, and answers user questions by fetching relevant articles and processing them via Google Gemini's LLM API.

The architecture is domain-agnostic. It currently supports the Penal Code out of the box, but can be scaled to any legal field (Commerce, Civil, etc.) by modifying the domain configuration and dropping new PDFs in the `mohami_data` folder.

## Project Structure & Roles

### 1. Data Ingestion & Processing
- **`pdf_extractor.py`**: The generic core engine for parsing legal PDFs. It slices PDFs into structured JSON articles and handles text normalization.
- **`mohami_data/`**: Directory where raw PDF files and their specific extraction wrappers live.
  - `mohami_data/penal_code/extract_penal.py`: Points the pdf_extractor at the Penal Code PDF with specific start/end markers.
  - `mohami_data/penal_code/extract_cpp.py`: Points the pdf_extractor at the Code of Criminal Procedure PDF.
- **`merge_corpus.py`**: Automatically discovers all extracted `code_*.json` files in the root folder and merges them into a unified `corpus.json`.

### 2. Search & Retrieval Core
- **`rag_utils.py`**: The brain of the retrieval system. It handles chunk deduplication, TF-IDF / BM25 hybrid search, semantic search scoring, and rule-based topic boosting.
- **`encode_query_server.py`**: A local background server that stays in memory to perform rapid SentenceTransformer embeddings. This avoids reloading the heavy PyTorch embedding model on every single query.
- **`index_corpus.py`**: Reads the `corpus.json` file and calculates the dense vector embeddings for all articles, caching them in `embeddings_cache.npz` to make search lightning fast.

### 3. Orchestration & LLM
- **`answer.py`**: The main entrypoint. Takes a user's question, asks `rag_utils` for the top legal articles, frames the context, and sends it to Google Gemini (`gemini-2.5-flash`) to generate the final human-readable answer.
- **`api.py`**: A FastAPI wrapper that turns the RAG system into a REST API (`POST /ask`).
- **`domain_config.json`**: The externalized configuration file defining the system prompt, law-specific synonyms for search expansion, and forced topical boosts (e.g., forcing arrest rights articles on certain keywords).

### 4. Utilities
- **`rebuild_all.py`**: The master build script. It auto-discovers all `extract*.py` scripts, builds the JSONs, merges the corpus, and rebuilds the embedding index in one command.
- **`check_groq.py`**: A diagnostic tool to ensure your `MOHAMI_GEMINI_API_KEY` is configured correctly and the target LLM is available.
- **`download_embedding_model.py`**: Fetches and caches the required sentence transformers locally.

## Getting Started

1. **Ensure your Gemini API key is set**:
   ```powershell
   $env:MOHAMI_GEMINI_API_KEY="your_key_here"
   ```
2. **Start the local embedding server** (Required for fast response times):
   ```powershell
   python encode_query_server.py
   ```
3. **In a new terminal, ask a legal question**:
   ```powershell
   python answer.py "Quelle est la peine pour un vol qualifie ?"
   ```

## Adding a New Legal Domain

To expand MOHAMI beyond the Penal Code:
1. Create a new folder (e.g., `mohami_data/commerce_code/`).
2. Add your PDF inside it.
3. Create a wrapper script (e.g., `extract_commerce.py`) that imports `pdf_extractor.py` and specifies the start markers for your PDF.
4. Update `domain_config.json` with new synonyms or prompts if needed.
5. Run `python rebuild_all.py`.
