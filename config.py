"""Local configuration; never display or persist credentials in app output."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env.local", override=False)
load_dotenv(ROOT / ".env", override=False)


def settings():
    try:
        similarity = float(os.getenv("RAG_MIN_SIMILARITY", "0.30"))
    except ValueError:
        similarity = 0.30
    return {
        "api_key": os.getenv("OPENAI_API_KEY", "").strip(),
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        "min_similarity": min(1.0, max(0.0, similarity)),
    }


def make_client():
    from openai import OpenAI
    key = settings()["api_key"]
    if not key:
        raise ValueError("Live analysis needs an OpenAI API key. Use Sample demo to try the included reports.")
    return OpenAI(api_key=key, timeout=60.0, max_retries=1)
