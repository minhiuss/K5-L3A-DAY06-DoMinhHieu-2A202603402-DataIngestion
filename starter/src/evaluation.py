"""Evaluate retrieved evidence and preserve per-query traces."""
import re
from typing import Any


def match_text(text: str) -> str:
    """Lower-case, straight quotes, one space: so line breaks and quote styles do not block a match."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def is_hit(question: dict[str, Any], hit: dict[str, Any]) -> bool:
    """A hit = right source AND right page AND the chunk contains the whole evidence quote.

    Alternative gold evidence can be listed in question["alt_gold"] as
    [{"gold_source_id", "gold_page", "evidence_quote"}, ...]; any one of them counts.
    """
    golds = [question] + list(question.get("alt_gold", []))
    for gold in golds:
        if (hit["document_id"] == gold["gold_source_id"]
                and hit["page"] == gold["gold_page"]
                and match_text(gold["evidence_quote"]) in match_text(hit["text"])):
            return True
    return False


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and enough gold evidence; keep hit@1 and hit@3 trace.

    Accept any documented alternative gold evidence. Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    flags = [is_hit(question, h) for h in hits]
    gold_page_seen = any(h["page"] == question["gold_page"] for h in hits)
    flt = question.get("filter")
    return {
        "id": question["id"],
        "split": question["split"],
        "type": question.get("type"),
        "question": question["question"],
        "filter": flt,
        "gold_page": question["gold_page"],
        "evidence_quote": question["evidence_quote"],
        "hit1": bool(flags[:1] and flags[0]),
        "hit3": any(flags[:3]),
        "first_hit_rank": flags.index(True) + 1 if True in flags else None,
        "gold_page_no_full_quote": gold_page_seen and not any(flags),
        "filter_ok": (all(all(h["metadata"].get(k) == v for k, v in flt.items()) for h in hits) if flt else None),
        "hits": [{"rank": i + 1, "chunk_id": h["chunk_id"], "document_id": h["document_id"], "source": h["source"],
                  "page": h["page"], "metadata": h["metadata"], "score": round(h["score"], 4),
                  "is_hit": f, "text": h["text"]} for i, (h, f) in enumerate(zip(hits, flags))],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split (n/N, not only %)."""
    out: dict[str, Any] = {}
    for t in traces:
        key = f"{t['strategy']}/{t['split']}"
        s = out.setdefault(key, {"N": 0, "hit1": 0, "hit3": 0, "filter_N": 0, "filter_ok": 0})
        s["N"] += 1
        s["hit1"] += t["hit1"]
        s["hit3"] += t["hit3"]
        if t["filter"]:
            s["filter_N"] += 1
            s["filter_ok"] += bool(t["filter_ok"])
    for s in out.values():
        s["hit1_str"] = f"{s['hit1']}/{s['N']}"
        s["hit3_str"] = f"{s['hit3']}/{s['N']}"
        s["filter_str"] = f"{s['filter_ok']}/{s['filter_N']}" if s["filter_N"] else "N/A"
    return out
