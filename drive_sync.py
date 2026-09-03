from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import gdown
import requests
from dotenv import load_dotenv
from filelock import FileLock, Timeout

from document_processing import SUPPORTED_EXTENSIONS


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = PROJECT_DIR / ".drive-cache"
MANIFEST_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": MANIFEST_VERSION, "files": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": MANIFEST_VERSION, "files": {}}
    if payload.get("version") != MANIFEST_VERSION or not isinstance(payload.get("files"), dict):
        return {"version": MANIFEST_VERSION, "files": {}}
    return payload


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def safe_extract_zip(archive: Path, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    extracted: list[Path] = []
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if member.is_dir():
                continue
            target = (destination / member.filename).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"Unsafe ZIP member rejected: {member.filename}")
            if target.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("wb") as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
            extracted.append(target)
    return extracted


def download_folder(folder_url: str, destination: Path, discover_only: bool) -> list[Path]:
    result = gdown.download_folder(
        url=folder_url,
        output=str(destination),
        quiet=False,
        use_cookies=False,
        remaining_ok=True,
        skip_download=discover_only,
        resume=True,
    )
    if result is None:
        raise RuntimeError(
            "Google Drive did not return the folder. Confirm that anyone with the link can view it."
        )
    if discover_only:
        for item in result:
            print(item.path)
        print(f"Discoverable Drive files: {len(result)}")
        return []
    return [Path(value) for value in result]


def collect_documents(downloaded: list[Path], cache_dir: Path) -> list[Path]:
    extracted_root = cache_dir / "extracted"
    candidates: list[Path] = []
    for original_path in downloaded:
        path = normalize_downloaded_file(original_path, cache_dir)
        suffix = path.suffix.lower()
        if suffix == ".zip":
            candidates.extend(safe_extract_zip(path, extracted_root / path.stem))
        elif suffix in SUPPORTED_EXTENSIONS:
            candidates.append(path)

    unique: dict[str, Path] = {}
    for path in candidates:
        unique.setdefault(sha256_file(path), path)
    def priority(value: Path) -> tuple[int, int, str]:
        suffix = value.suffix.lower()
        group = 0 if suffix in {".json", ".xlsx", ".csv", ".txt", ".md"} else 1
        if suffix in {".png", ".jpg", ".jpeg"}:
            group = 2
        return group, value.stat().st_size, str(value).lower()

    return sorted(unique.values(), key=priority)


def normalize_downloaded_file(path: Path, cache_dir: Path) -> Path:
    if path.suffix or not zipfile.is_zipfile(path):
        return path
    with zipfile.ZipFile(path) as bundle:
        if "xl/workbook.xml" not in bundle.namelist():
            return path
    native_dir = cache_dir / "extracted" / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    target = native_dir / f"{path.name}.xlsx"
    shutil.copy2(path, target)
    return target


def api_json(session: requests.Session, method: str, url: str, **kwargs: Any) -> Any:
    response = session.request(method, url, timeout=120, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"RAG API returned HTTP {response.status_code}: {response.text[:1000]}")
    return response.json()


def wait_for_job(session: requests.Session, api_url: str, job_id: str, poll_seconds: float) -> dict[str, Any]:
    while True:
        payload = api_json(session, "GET", f"{api_url}/v1/ingestion-jobs")
        jobs = payload.get("data", payload) if isinstance(payload, dict) else payload
        job = next((item for item in jobs if item.get("id") == job_id), None)
        if not job:
            raise RuntimeError(f"Ingestion job disappeared: {job_id}")
        print(f"  {job.get('phase', job.get('status'))}: {job.get('progress', 0)}%", end="\r", flush=True)
        if job.get("status") in {"ready", "failed"}:
            print()
            return job
        time.sleep(poll_seconds)


def ingest_file(
    session: requests.Session,
    api_url: str,
    path: Path,
    source: str,
    poll_seconds: float,
) -> dict[str, Any]:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        job = api_json(
            session,
            "POST",
            f"{api_url}/v1/ingestion-jobs",
            files={"file": (path.name, handle, media_type)},
            data={"source": source},
        )
    if job.get("status") in {"ready", "failed"}:
        return job
    return wait_for_job(session, api_url, job["id"], poll_seconds)


def relative_source(path: Path, cache_dir: Path) -> str:
    for base in (cache_dir / "download", cache_dir / "extracted"):
        try:
            relative = path.resolve().relative_to(base.resolve())
            return f"Google Drive / {relative.as_posix()}"
        except ValueError:
            continue
    return f"Google Drive / {path.name}"


def run(args: argparse.Namespace) -> int:
    load_dotenv(PROJECT_DIR / ".env")
    folder_url = args.folder_url or os.getenv("GOOGLE_DRIVE_FOLDER_URL", "").strip()
    api_key = os.getenv("RAG_API_KEY", "").strip()
    if not folder_url:
        raise RuntimeError("Set GOOGLE_DRIVE_FOLDER_URL in .env or pass --folder-url.")
    if not api_key and not args.discover_only:
        raise RuntimeError("RAG_API_KEY is missing from .env.")

    cache_dir = Path(args.cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(cache_dir / "sync.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        print("A Google Drive sync is already running.")
        return 0

    try:
        downloaded = download_folder(folder_url, cache_dir / "download", args.discover_only)
        if args.discover_only:
            return 0

        documents = collect_documents(downloaded, cache_dir)
        if args.max_files:
            documents = documents[: args.max_files]
        print(f"Unique supported documents found: {len(documents)}")

        manifest_path = cache_dir / "sync-state.json"
        manifest = load_manifest(manifest_path)
        session = requests.Session()
        session.headers["X-API-Key"] = api_key
        health = api_json(session, "GET", f"{args.api_url}/health/ready")
        if health.get("status") not in {"ready", "healthy"}:
            raise RuntimeError(f"Local RAG is not ready: {health}")

        completed = skipped = failed = 0
        for index, path in enumerate(documents, start=1):
            digest = sha256_file(path)
            state = manifest["files"].get(digest)
            if state and state.get("status") == "ready":
                skipped += 1
                continue
            source = relative_source(path, cache_dir)
            print(f"[{index}/{len(documents)}] {source}")
            try:
                job = ingest_file(session, args.api_url, path, source, args.poll_seconds)
                status = job.get("status")
                manifest["files"][digest] = {
                    "status": status,
                    "source": source,
                    "document_id": job.get("document_id"),
                    "synced_at": int(time.time()),
                    "error": job.get("error"),
                }
                save_manifest(manifest_path, manifest)
                if status == "ready":
                    completed += 1
                else:
                    failed += 1
                    print(f"  Failed: {job.get('error', 'unknown ingestion error')}", file=sys.stderr)
            except Exception as exc:
                failed += 1
                manifest["files"][digest] = {
                    "status": "failed",
                    "source": source,
                    "synced_at": int(time.time()),
                    "error": str(exc),
                }
                save_manifest(manifest_path, manifest)
                print(f"  Failed: {exc}", file=sys.stderr)

        print(f"Drive sync complete. Ready: {completed}, unchanged: {skipped}, failed: {failed}")
        return 1 if failed else 0
    finally:
        lock.release()


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Synchronize a shared Google Drive folder into Local RAG.")
    value.add_argument("--folder-url", help="Google Drive folder sharing URL. Defaults to .env.")
    value.add_argument("--api-url", default="http://127.0.0.1:8000")
    value.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    value.add_argument("--poll-seconds", type=float, default=2.5)
    value.add_argument("--max-files", type=int, default=0, help="Process only the first N unique files.")
    value.add_argument("--discover-only", action="store_true", help="List Drive files without downloading them.")
    return value


if __name__ == "__main__":
    try:
        raise SystemExit(run(parser().parse_args()))
    except KeyboardInterrupt:
        print("Drive sync stopped. Run it again to resume.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Drive sync failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
