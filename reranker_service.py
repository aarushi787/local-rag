"""Optional localhost-only BGE cross-encoder reranking service."""

from __future__ import annotations

import os
from threading import Lock

from fastapi import FastAPI
from pydantic import BaseModel, Field
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


MODEL_NAME = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
MODEL_LOCK = Lock()
MODEL: AutoModelForSequenceClassification | None = None
TOKENIZER: AutoTokenizer | None = None
app = FastAPI(title="Local RAG Cross Encoder")


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    documents: list[str] = Field(min_length=1, max_length=50)


def get_model() -> tuple[AutoTokenizer, AutoModelForSequenceClassification]:
    global MODEL, TOKENIZER
    with MODEL_LOCK:
        if MODEL is None:
            TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)
            MODEL = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
            MODEL.eval()
        assert TOKENIZER is not None
        return TOKENIZER, MODEL


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME, "loaded": MODEL is not None}


@app.post("/rerank")
def rerank(request: RerankRequest) -> dict:
    pairs = [(request.query, document) for document in request.documents]
    tokenizer, model = get_model()
    inputs = tokenizer(
        pairs, padding=True, truncation=True, return_tensors="pt", max_length=512
    )
    with torch.no_grad():
        raw_scores = model(**inputs, return_dict=True).logits.view(-1).float()
        scores = torch.sigmoid(raw_scores)
    return {"scores": [float(score) for score in scores]}
