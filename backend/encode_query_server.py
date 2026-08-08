"""Persistent query encoder: load the model once, encode many questions."""

import json
import os
import sys

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from rag_utils import _load_embedding_model, encode_texts


def main() -> None:
    model, model_name = _load_embedding_model()
    sys.stderr.write(f"encoder-ready:{model_name}\n")
    sys.stderr.flush()

    for line in sys.stdin:
        question = line.strip()
        if not question:
            continue
        if question.lower() in {"__quit__", "quit", "exit"}:
            break
        vector = encode_texts(model, model_name, [question], is_query=True)[0]
        sys.stdout.write(json.dumps(vector) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
