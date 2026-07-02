"""Download the preferred embedding model (run once with internet)."""

from sentence_transformers import SentenceTransformer

from rag_utils import EMBEDDING_MODELS


def main() -> None:
    for model_name in EMBEDDING_MODELS:
        try:
            print(f"Downloading {model_name}...")
            SentenceTransformer(model_name, device="cpu", local_files_only=False)
            print(f"OK: {model_name}")
            return
        except Exception as exc:
            print(f"Failed: {model_name} -> {exc}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
