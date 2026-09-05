"""Compare Local RAG response profiles through the public API."""

from __future__ import annotations

import argparse
import os
import statistics
import time

import requests
from dotenv import load_dotenv


load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Fast, Balanced, and Quality modes.")
    parser.add_argument(
        "--question",
        default="Which models are used in the local RAG workflow?",
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=60)
    parser.add_argument("--document-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--profiles",
        default="auto,fast,balanced,quality",
        help="Comma-separated profile IDs to benchmark",
    )
    args = parser.parse_args()

    api_key = os.getenv("RAG_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("RAG_API_KEY is not configured in .env")
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    profile_response = requests.get(
        f"{args.base_url}/v1/profiles", headers=headers, timeout=15
    )
    profile_response.raise_for_status()
    selected = {value.strip() for value in args.profiles.split(",") if value.strip()}
    profiles = [item for item in profile_response.json()["data"] if item["id"] in selected]
    print("profile   model                   total_s  retrieval_s  embed_s  search_s  load_s  gen_tok_s")
    print("-------   ----------------------  -------  -----------  -------  --------  ------  ---------")
    for profile in profiles:
        if not profile["available"]:
            print(f"{profile['id']:<9} {profile['model']:<22} unavailable")
            continue
        measurements: list[dict] = []
        for _ in range(max(args.runs, 1)):
            payload = {
                "model": profile["model"],
                "profile": profile["id"],
                "messages": [{"role": "user", "content": args.question}],
                "stream": False,
                "save": False,
                "use_cache": False,
                "max_tokens": args.max_tokens,
            }
            if args.document_id:
                payload["document_id"] = args.document_id
            started = time.perf_counter()
            response = requests.post(
                f"{args.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=360,
            )
            response.raise_for_status()
            result = response.json()
            measurements.append(
                {
                    "total": time.perf_counter() - started,
                    "retrieval": (result.get("metrics", {}).get("retrieval_ms") or 0) / 1000,
                    "embedding": (result.get("metrics", {}).get("query_embedding_ms") or 0) / 1000,
                    "search": (result.get("metrics", {}).get("hybrid_search_ms") or 0) / 1000,
                    "load": (result.get("metrics", {}).get("load_ms") or 0) / 1000,
                    "generation": result.get("metrics", {}).get("generation_tokens_per_second") or 0,
                }
            )
        total = statistics.mean(item["total"] for item in measurements)
        retrieval = statistics.mean(item["retrieval"] for item in measurements)
        embedding = statistics.mean(item["embedding"] for item in measurements)
        search = statistics.mean(item["search"] for item in measurements)
        load = statistics.mean(item["load"] for item in measurements)
        generation = statistics.mean(item["generation"] for item in measurements)
        print(
            f"{profile['id']:<9} {profile['model']:<22} {total:>7.2f}  "
            f"{retrieval:>11.2f}  {embedding:>7.2f}  {search:>8.2f}  "
            f"{load:>6.2f}  {generation:>9.2f}"
        )


if __name__ == "__main__":
    main()
