"""Repeatable laptop-safe baseline probe. No startup migrations or DB writes.

Uses existing application functions directly; does NOT measure HTTP/auth latency.
Legacy question scores are proxies. Requires >=2 GiB free RAM before each request.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def percentiles(values):
    ordered = sorted(values)
    return {"n": len(values), "p50_ms": statistics.median(ordered) if ordered else None,
            "p95_ms": ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-generation", action="store_true")
    args = parser.parse_args()
    report = {"status": "running", "transport": "direct Python functions, HTTP excluded",
              "dataset_review": "unverified legacy proxies", "retrieval": {}, "profiles": {}}
    free = psutil.virtual_memory().available / 1024**3
    report["available_ram_gib"] = round(free, 3)
    if free < 2:
        report.update(status="blocked", reason="Need at least 2 GiB available RAM before live benchmark")
        print(json.dumps(report, indent=2))
        raise SystemExit(2)
    import app
    original_configure = app.configure_database_connection
    def configure(conn):
        conn.read_only = True
        original_configure(conn)
    app.configure_database_connection = configure
    dataset = ROOT / "evaluation_questions.jsonl"
    examples = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    report["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
    def guard():
        if psutil.virtual_memory().available < 2 * 1024**3:
            raise MemoryError("Benchmark memory guard")
    try:
        app.open_database_pool()
        with app.db_connection() as conn:
            report["read_only"] = conn.execute("SHOW transaction_read_only").fetchone()[0]
            report["corpus_version"] = conn.execute("SELECT version FROM rag_corpus_state WHERE id=1").fetchone()[0]
        for pipeline in ("baseline", "upgraded"):
            records = []
            report["retrieval"][pipeline] = {"records": records}
            app.cached_query_embedding.cache_clear()
            for n, item in enumerate(examples, 1):
                guard()
                stages, start = {}, time.perf_counter()
                rows = app.retrieve_baseline(item["question"], 5) if pipeline == "baseline" else app.retrieve(item["question"], 5, timings=stages)
                records.append({"row": n, "score": app.score_retrieval(item, rows),
                                "should_refuse": bool(item.get("should_refuse")), "stages": stages,
                                "latency_ms": (time.perf_counter() - start) * 1000})
            report["retrieval"][pipeline]["latency"] = percentiles([r["latency_ms"] for r in records])
        if not args.skip_generation:
            installed = {m["name"] for m in app.ollama_get("/api/tags").get("models", [])}
            principal = app.Principal(app.MASTER_USER_ID, "Read-only benchmark", "admin")
            for profile, settings in app.PROFILE_CONFIG.items():
                if settings["model"] not in installed:
                    report["profiles"][profile] = {"status": "model_unavailable"}
                    continue
                runs = []
                report["profiles"][profile] = {"status": "measuring", "runs": runs}
                for _ in range(3):
                    guard()
                    question = examples[3]
                    request = app.ChatCompletionRequest(model=settings["model"], profile=profile, max_tokens=80,
                        temperature=.1, stream=True, save=False, use_cache=False,
                        messages=[app.ChatMessage(role="user", content=question["question"])])
                    start, first, text, sources, metrics = time.perf_counter(), None, "", [], {}
                    stream = app.streaming_chat(request, principal)
                    try:
                        for part in stream:
                            if psutil.virtual_memory().available < .75 * 1024**3:
                                raise MemoryError("Generation memory guard")
                            for line in part.splitlines():
                                if not line.startswith("data: ") or line == "data: [DONE]":
                                    continue
                                event = json.loads(line[6:])
                                if event.get("error"):
                                    raise RuntimeError("Generation failed")
                                delta = event.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta and first is None:
                                    first = (time.perf_counter() - start) * 1000
                                text += delta
                                sources = event.get("sources", sources)
                                metrics = event.get("metrics", metrics)
                    finally:
                        stream.close()
                    # Do not persist document or answer text in benchmark logs.
                    metrics.pop("grounding_validation", None)
                    runs.append({"first_text_ms": first, "total_ms": (time.perf_counter() - start) * 1000,
                                 "metrics": metrics, "quality_proxy": app.score_generated_answer(question, text, sources)})
                report["profiles"][profile]["status"] = "measured"
        with app.db_connection() as conn:
            report["corpus_version_end"] = conn.execute("SELECT version FROM rag_corpus_state WHERE id=1").fetchone()[0]
        report["status"] = "measured"
    except Exception as exc:
        report.update(status="blocked" if isinstance(exc, MemoryError) else "failed", error_type=type(exc).__name__)
    finally:
        app.shutdown()
        report["available_ram_end_gib"] = round(psutil.virtual_memory().available / 1024**3, 3)
        print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "measured" else 2)


if __name__ == "__main__":
    main()
