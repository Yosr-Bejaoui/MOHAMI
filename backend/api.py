import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure we can import answer.py from the same directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from .answer import answer_question

app = FastAPI(title="MOHAMI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/ask")
def ask(req: AskRequest):
    answer_text, hits, domain = answer_question(req.question)
    
    sources = []
    for hit in hits:
        metadata = hit.get("metadata", {})
        sources.append({
            "article": metadata.get("article_number", "?"),
            "law": metadata.get("law", "Inconnu"),
            "excerpt": hit.get("text", "")
        })
        
    return {
        "answer": answer_text,
        "sources": sources,
        "detected_domain": domain
    }

frontend_path = PROJECT_ROOT / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
