"""Measure streaming first-token and component latency through the public RAG API."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time

import requests
from dotenv import load_dotenv


load_dotenv()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def run_once(base_url: str, headers: dict[str, str], payload: dict) -> dict:
    started = time.perf_counter()
    first_token = None
    metrics: dict = {}
    statuses: list[str] = []
    with requests.post(
        f"{base_url}/v1/chat/completions",
        headers=headers,
        json=payload,
        stream=True,
        timeout=360,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            event = json.loads(raw)
            if event.get("error"):
                raise RuntimeError(event["error"].get("message", "stream failed"))
            if event.get("object") == "rag.status":
                statuses.append(event.get("stage", "working"))
            if event.get("choices", [{}])[0].get("delta", {}).get("content") and first_token is None:
                first_token = (time.perf_counter() - started) * 1000
            if event.get("metrics"):
                metrics = event["metrics"]
    return {
        **metrics,
        "client_first_token_ms": round(first_token or 0.0, 2),
        "client_total_ms": round((time.perf_counter() - started) * 1000, 2),
        "statuses": statuses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--profile", default="fast", choices=("auto", "fast", "balanced", "quality"))
    parser.add_argument("--question", default="Which models are used in the local RAG workflow?")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=80)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("RAG_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("RAG_API_KEY is not configured")
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    payload = {
        "model": "local-rag",
        "profile": args.profile,
        "messages": [{"role": "user", "content": args.question}],
        "stream": True,
        "save": False,
        "use_cache": False,
        "max_tokens": args.max_tokens,
    }
    results = [run_once(args.base_url, headers, payload) for _ in range(max(args.runs, 1))]
    if args.json:
        print(json.dumps(results, indent=2))
        return

    fields = (
        "client_first_token_ms", "client_total_ms", "cache_lookup_ms", "retrieval_ms",
        "query_embedding_ms", "hybrid_search_ms", "context_enrichment_ms", "load_ms",
    )
    print(f"Profile: {args.profile}; runs: {len(results)}")
    for field in fields:
        values = [float(result.get(field) or 0) for result in results]
        print(
            f"{field:<28} p50={statistics.median(values):>9.2f}  "
            f"p95={percentile(values, 0.95):>9.2f}"
        )
    rates = [float(result.get("generation_tokens_per_second") or 0) for result in results]
    print(f"generation_tokens_per_second p50={statistics.median(rates):.2f}")
    print(f"intent={results[-1].get('intent')} statuses={','.join(results[-1].get('statuses', []))}")


if __name__ == "__main__":
    main()
