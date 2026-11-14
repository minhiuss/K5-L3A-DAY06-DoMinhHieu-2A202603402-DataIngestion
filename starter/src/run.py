"""Day 06 pipeline: load -> normalize -> tag -> chunk A/B -> embed -> store -> run A/B/C -> score."""
import csv
import json
import os
import platform
import statistics
import time
from importlib.metadata import version
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, match_text, summarize
from .ingestion import add_section_metadata, load_pdf, normalize_text
from .store import PgVectorStore

STARTER = Path(__file__).resolve().parents[1]
REPO = STARTER.parent
RESULTS = STARTER / "results"
PDF = STARTER / "data" / "Workplace_Software_and_Skills_-_WEB_IlfJtcP.pdf"
DOCUMENT_ID = "openstax-wss-ch3"
FIRST_PAGE, LAST_PAGE = 148, 218
CONFIG = {
    "A": {"chunking": "fixed_size", "size": 500, "overlap": 50, "stored_as": "A", "use_filter": False},
    "B": {"chunking": "by_paragraph", "max_size": 800, "stored_as": "B", "use_filter": False},
    "C": {"chunking": "by_paragraph", "max_size": 800, "stored_as": "B", "use_filter": True},
}
TOP_K = 3


def chunk_stats(chunks):
    lengths = [len(c.text) for c in chunks]
    return {"count": len(chunks), "min": min(lengths), "mean": round(statistics.mean(lengths), 1),
            "median": statistics.median(lengths), "max": max(lengths), "total_chars": sum(lengths)}


def row_count(url, strategy):
    with psycopg.connect(url) as conn:
        return conn.execute("SELECT count(*) FROM chunks WHERE strategy = %s", [strategy]).fetchone()[0]


def coherence_sample(parts, chunks_by_strategy):
    """10 positions fixed before scoring: the middle of the first part of PDF pages 148-157."""
    rows = []
    first_parts = {}
    for p in parts:
        first_parts.setdefault(p.page, p)
    for page in range(FIRST_PAGE, FIRST_PAGE + 10):
        text = first_parts[page].text
        mid = len(text) // 2
        snippet = text[mid:mid + 40]
        for strategy in ("A", "B"):
            found = next((c for c in chunks_by_strategy[strategy]
                          if c.page == page and match_text(snippet) in match_text(c.text)), None)
            rows.append({"position": f"p{page}@{mid}", "snippet": snippet, "strategy": strategy,
                         "chunk_id": found.chunk_id if found else "", "chunk_text": found.text if found else "",
                         "score_0_1_2": "", "reason": ""})
    return rows


def main() -> None:
    load_dotenv(STARTER / ".env")
    url = os.getenv("DATABASE_URL")
    model_name = os.getenv("EMBEDDING_MODEL") or "sentence-transformers/all-MiniLM-L6-v2"
    RESULTS.mkdir(exist_ok=True)
    log = {"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "python": platform.python_version(),
           "versions": {p: version(p) for p in ("sentence-transformers", "torch", "pypdf", "psycopg")},
           "model": model_name, "cost_usd": 0, "top_k": TOP_K, "config": CONFIG}

    t0 = time.perf_counter()
    pages = load_pdf(PDF, DOCUMENT_ID, PDF.name)
    counted = [p for p in pages if FIRST_PAGE <= p.page <= LAST_PAGE]
    for p in counted:
        p.text = normalize_text(p.text)
    empty = [p.page for p in counted if not p.text.strip()]
    parts = add_section_metadata(counted)
    log["pages"] = {"physical_total": len(pages), "counted": len(counted), "empty_in_counted": empty,
                    "parts_after_section_split": len(parts),
                    "chars_per_page": {p.page: len(p.text) for p in counted},
                    "total_chars": sum(len(p.text) for p in counted),
                    "min_chars_page": min(len(p.text) for p in counted)}
    log["load_seconds"] = round(time.perf_counter() - t0, 2)

    chunks = {"A": [c for p in parts for c in fixed_size(p, CONFIG["A"]["size"], CONFIG["A"]["overlap"])],
              "B": [c for p in parts for c in by_paragraph(p, CONFIG["B"]["max_size"])]}
    log["chunks"] = {s: chunk_stats(c) for s, c in chunks.items()}

    embedder = MyEmbedder(model_name)
    store = PgVectorStore(url, embedder.dimensions)
    store.create_schema()
    log["dimensions"] = embedder.dimensions
    log["ingest"] = {}
    for s, cs in chunks.items():
        t0 = time.perf_counter()
        vectors = embedder.embed_documents([c.text for c in cs])
        embed_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        store.upsert(s, cs, vectors)
        first = row_count(url, s)
        store.upsert(s, cs, vectors)
        second = row_count(url, s)
        log["ingest"][s] = {"embed_seconds": round(embed_s, 2), "upsert_seconds_x2": round(time.perf_counter() - t0, 2),
                            "rows_after_1st": first, "rows_after_2nd": second, "duplicates": second - len(cs)}

    bench = json.loads((REPO / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    questions = bench["questions"]
    traces = []
    t0 = time.perf_counter()
    for q in questions:
        qv = embedder.embed_query(q["question"])
        for s, cfg in CONFIG.items():
            flt = q.get("filter") if cfg["use_filter"] else None
            hits = store.search(cfg["stored_as"], qv, TOP_K, flt)
            tr = evaluate_query(q, hits)
            tr["strategy"] = s
            tr["filter_applied"] = flt
            if not cfg["use_filter"]:
                tr["filter_ok"] = (all(all(h["metadata"].get(k) == v for k, v in q["filter"].items())
                                       for h in tr["hits"]) if q.get("filter") else None)
            traces.append(tr)
    log["query_seconds_all"] = round(time.perf_counter() - t0, 2)

    metrics = summarize(traces)
    dev = {s: metrics[f"{s}/dev"] for s in CONFIG}
    ranked = sorted(CONFIG, key=lambda s: (dev[s]["hit3"], dev[s]["hit1"], dev[s]["filter_ok"],
                                           -log["chunks"][CONFIG[s]["stored_as"]]["count"]), reverse=True)
    best = ranked[0]
    ties = [s for s in CONFIG if s != best and dev[best]["hit3"] - dev[s]["hit3"] <= 1]
    log["selection"] = {"rule": bench["meta"]["selection_rule"], "dev_ranking": ranked, "chosen": best,
                        "within_1_question_on_hit3": ties}

    with open(RESULTS / "traces.jsonl", "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    (RESULTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (RESULTS / "run_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")

    if not (RESULTS / "audit_coherence.csv").exists():
        with open(RESULTS / "audit_coherence.csv", "w", newline="", encoding="utf-8-sig") as f:
            rows = coherence_sample(parts, chunks)
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
    if (RESULTS / "audit_metadata_grounding.csv").exists():
        return print_summary(metrics, best, ties, log)
    with open(RESULTS / "audit_metadata_grounding.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["strategy", "id", "question", "filter", "gold_page", "rank", "chunk_id", "page", "section",
                    "platform", "auto_hit", "metadata_correct_Y_N", "grounding_0_1_2_per_question", "reason", "text"])
        for t in traces:
            if t["split"] != "test":
                continue
            for h in t["hits"]:
                w.writerow([t["strategy"], t["id"], t["question"], json.dumps(t["filter"]), t["gold_page"], h["rank"],
                            h["chunk_id"], h["page"], h["metadata"]["section"], h["metadata"]["platform"],
                            h["is_hit"], "", "", "", h["text"][:300]])
    print_summary(metrics, best, ties, log)


def print_summary(metrics, best, ties, log) -> None:
    """Print Hit@1 / Hit@3 / filter compliance per strategy and split, plus the dev choice."""
    for split in ("dev", "test"):
        for s in CONFIG:
            m = metrics[f"{s}/{split}"]
            print(f"{s} {split:4} Hit@1 {m['hit1_str']:6} Hit@3 {m['hit3_str']:6} filter {m['filter_str']}")
    print("chosen on dev:", best, "| within 1 question:", ties)
    print("chunks:", {s: v["count"] for s, v in log["chunks"].items()}, "| duplicates:",
          {s: v["duplicates"] for s, v in log["ingest"].items()})


if __name__ == "__main__":
    main()
