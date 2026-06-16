#!/usr/bin/env python3
"""search_wiki.py — Semantic search a wiki project via LanceDB vector index.

Requires embeddings built first: build_embeddings.py --project <path> embed

Backend: local Ollama bge-m3 by default. Configurable via env:
  EMBEDDING_BASE_URL  — default http://127.0.0.1:11434/v1
  EMBEDDING_MODEL     — default bge-m3

Usage:
  search_wiki.py "query" --project ~/Documents/知识库/HardwareWiki
  search_wiki.py "LC谐振" --project ~/Documents/知识库/硬件设计知识库 --top 10
"""
import argparse, json, os, sys, urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic search a wiki project via LanceDB")
    parser.add_argument("query", help="Search query (natural language)")
    parser.add_argument("--project", required=True, help="Path to wiki project root")
    parser.add_argument("--top", type=int, default=5, help="Max results (default: 5)")
    args = parser.parse_args()

    project = Path(args.project).expanduser()

    # Use shared runtime detection (NashSU-aligned: .llm-wiki/)
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    if _script_dir not in sys.path:
        sys.path.insert(0, _script_dir)
    from _paths import detect_runtime_dir
    runtime = detect_runtime_dir(project)

    lancedb_dir = runtime / "lancedb"
    if not lancedb_dir.exists():
        print(f"ERROR: LanceDB not found at {lancedb_dir}", file=sys.stderr)
        print("  Run: build_embeddings.py --project <path> embed", file=sys.stderr)
        return 1

    try:
        import lancedb
    except ImportError:
        print("ERROR: lancedb not installed. Run: pip install lancedb", file=sys.stderr)
        return 1

    # Embedding backend (same env vars as build_embeddings.py)
    base_url = os.environ.get("EMBEDDING_BASE_URL", "http://127.0.0.1:11434/v1")
    model = os.environ.get("EMBEDDING_MODEL", "bge-m3")
    api_key = os.environ.get("EMBEDDING_API_KEY", "")

    # Embed query
    body = json.dumps({"model": model, "input": [args.query]}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = f"{base_url.rstrip('/')}/embeddings"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        qvec = data["data"][0]["embedding"]
    except Exception as e:
        print(f"ERROR: Embedding API failed: {e}", file=sys.stderr)
        return 1

    # Search LanceDB
    try:
        db = lancedb.connect(str(lancedb_dir))
        tbl = db.open_table("wiki_chunks")
        df = tbl.search(qvec).limit(args.top).to_pandas()
    except Exception as e:
        print(f"ERROR: LanceDB search failed: {e}", file=sys.stderr)
        return 1

    if df.empty:
        print(f"No results for: {args.query}")
        return 1

    print(f"{len(df)} results for: {args.query}\n")
    for i, (_, row) in enumerate(df.iterrows()):
        dist = row.get("_distance", 0)
        sim = 1.0 / (1.0 + float(dist))
        title = row.get("title", "") or row.get("heading_path", "") or ""
        title_str = f"  ({title})" if title else ""
        print(f"{i + 1}. [{sim:.3f}] wiki/{row['path']}{title_str}")
        snippet = str(row.get("chunk_text", ""))[:250].replace("\n", " ")
        print(f"   {snippet}...\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
