import argparse

from rag_utils import index_articles, is_index_ready


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MOHAMI embedding index.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if embeddings_cache.npz already exists.",
    )
    args = parser.parse_args()

    if is_index_ready() and not args.force:
        print("Index already exists. Use --force to rebuild.")
        return

    count = index_articles(reset=True)
    print(f"Indexed {count} chunks into embeddings_cache.npz")


if __name__ == "__main__":
    main()
