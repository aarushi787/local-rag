import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
EMBEDDING_OLLAMA_URL = os.getenv("EMBEDDING_OLLAMA_URL", OLLAMA_URL).rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embeddinggemma")
DEFAULT_CHAT_MODEL = os.getenv("CHAT_MODEL", "gemma4:e2b-it-qat")

# Add other configurations here...
