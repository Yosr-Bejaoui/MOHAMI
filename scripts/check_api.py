"""Check Gemini setup for MOHAMI."""

import json
import urllib.error
import urllib.request

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.rag_utils import GEMINI_API_KEY, GEMINI_BASE_URL, GEMINI_MODEL, is_gemini_available


def main() -> None:
    print("MOHAMI Gemini check")
    print(f"URL: {GEMINI_BASE_URL}")
    print(f"Expected model: {GEMINI_MODEL}")
    print()

    if not GEMINI_API_KEY.strip():
        print("Status: API KEY MISSING")
        print()
        print("Set MOHAMI_GEMINI_API_KEY in your environment before running MOHAMI.")
        return

    if not is_gemini_available():
        print("Status: NOT AVAILABLE")
        print()
        print("Do this:")
        print("1. Confirm the Gemini API key is set in MOHAMI_GEMINI_API_KEY.")
        print("2. Confirm internet access to generativelanguage.googleapis.com.")
        print("3. Make sure the selected model exists in your Google AI Studio account.")
        return

    print("Status: READY")
    try:
        request = urllib.request.Request(
            f"{GEMINI_BASE_URL}/models?key={GEMINI_API_KEY}",
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
        print(f"Available models: {len(models)} total")
        if any(GEMINI_MODEL in name for name in models):
            print(f"OK: {GEMINI_MODEL} is available for MOHAMI.")
        else:
            print(f"Model not listed: {GEMINI_MODEL}")
            print(f"Available: {[m for m in models if 'gemini' in m][:10]}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Could not read models: {exc}")


if __name__ == "__main__":
    main()
