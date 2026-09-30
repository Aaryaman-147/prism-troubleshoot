"""
Architectural ablation on Samsung's REAL catalog, in the spec's Appendix C
section 5 format:

  Baseline  Full LLM deeplink mapping   -- the LLM sees the whole catalog and picks
  Variant A Hybrid BM25 + dense         -- our pipeline (calibrated thresholds)
  Variant B Pure rules-based            -- keyword (BM25) matching only, no embeddings

All three are scored on the same labelled probes (hand-written + generated
across every catalog type) with the same verdicts: correct / WRONG / abstain.
Latency is per action (the unit a deeplink is chosen for); cost is tokens.
"""
import copy
import json
import statistics
import time

from app.eval.calibrate import classify, evaluate, sweep, _memoized_embeddings
from app.pipeline.ordering import resolve_deeplinks


def _p95(xs):
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def timed_retrieval(index, probes, alpha, floor, margin) -> dict:
    counts = {"correct": 0, "wrong": 0, "abstain": 0}
    lat = []
    with _memoized_embeddings():
        for p in probes:
            action = {"actionName": p["actionName"], "description": "It will fix the reported issue",
                      "category": "auto", "stepGroups": [{"steps": list(p["steps"])}]}
            t = time.perf_counter()
            acts, _, _ = resolve_deeplinks([copy.deepcopy(action)], index,
                                           min_confidence=floor, margin=margin, alpha=alpha)
            lat.append((time.perf_counter() - t) * 1000)
            counts[classify(p, acts[0], index.catalog_by_uri)] += 1
    return {**counts, "latency_p95_ms": round(_p95(lat), 2), "tokens_per_query": 0}


CATALOG_PROMPT = """You map troubleshooting actions to device-settings deeplinks.
Below is the COMPLETE catalog (id | what it does | message | type). For each
action, return the ONE catalog id whose screen/operation the action needs, or
"none" if no entry fits (e.g. physical actions like cleaning a port).
Types: onURL = turns a setting ON, offURL = turns it OFF, updateURL = changes a value,
onClickURL = opens a page.

CATALOG:
{catalog}

ACTIONS:
{actions}

Return ONLY JSON: {{"picks": [{{"i": 0, "id": "DL-0001"}}, {{"i": 1, "id": "none"}}]}}"""


def catalog_lines(catalog: list[dict]) -> str:
    return "\n".join(f'{e["id"]} | {e.get("description", "")} | {e.get("message", "")} | {e.get("originalType")}'
                     for e in catalog if not e.get("deeplink", "").endswith("dummy_positive"))


def llm_mapping(probes, catalog: list[dict], generate_json, batch: int = 10, log=print) -> dict:
    """Baseline: the LLM picks from the full catalog (no retrieval). Uses one
    call per `batch` probes; latency is per call divided by the batch size."""
    by_id = {e["id"]: e for e in catalog}
    by_uri = {e["deeplink"]: e for e in catalog}
    cat_text = catalog_lines(catalog)
    counts = {"correct": 0, "wrong": 0, "abstain": 0, "errors": 0}
    per_action_ms, tokens = [], []
    for i in range(0, len(probes), batch):
        chunk = probes[i:i + batch]
        actions = "\n".join(f'{j}: {p["actionName"]} -- steps: {" / ".join(p["steps"])}' for j, p in enumerate(chunk))
        t = time.perf_counter()
        try:
            data, usage = generate_json(CATALOG_PROMPT.format(catalog=cat_text, actions=actions),
                                        max_output_tokens=800, required_keys=("picks",))
        except Exception as e:
            log(f"  batch {i // batch + 1} failed: {type(e).__name__}: {e}")
            counts["errors"] += len(chunk)
            continue
        ms = (time.perf_counter() - t) * 1000
        per_action_ms += [ms / len(chunk)] * len(chunk)
        tokens += [(usage.prompt_tokens + usage.completion_tokens) / len(chunk)] * len(chunk)
        picks = {int(p.get("i", -1)): str(p.get("id", "none")) for p in (data.get("picks") or []) if str(p.get("i", "")).lstrip("-").isdigit()}
        for j, p in enumerate(chunk):
            e = by_id.get(picks.get(j, "none"))
            action = {"stepGroups": [{"actionableDeeplink": {"deeplink": e["deeplink"]} if e else None}]}
            counts[classify(p, action, by_uri)] += 1
        log(f"  LLM batch {i // batch + 1}: {len(chunk)} probes, {ms:.0f} ms")
    return {**counts, "latency_p95_ms": round(_p95(per_action_ms), 1) if per_action_ms else None,
            "tokens_per_query": round(statistics.mean(tokens)) if tokens else None}


def render(n_probes: int, n_pos: int, a: dict, b: dict, b_best: dict | None, base: dict | None,
           cfg: tuple, model: str) -> str:
    def row(name, r, note):
        if r is None:
            return f"| {name} | same for all variants (see section 2) | not run (`--llm`) | | | {note} |"
        acc = f"{r['correct']} / {r['wrong']} / {r['abstain']}"
        lat = "n/a" if r.get("latency_p95_ms") is None else f"{r['latency_p95_ms']} ms"
        cost = "0 (local)" if not r.get("tokens_per_query") else f"~{r['tokens_per_query']} tokens"
        return f"| {name} | same for all variants (see section 2) | {acc} | {lat} | {cost} | {note} |"
    alpha, floor, margin = cfg
    lines = [
        "# Architectural Ablation Analysis (Samsung Appendix C, section 5)", "",
        f"Real catalog, {n_probes} labelled probes ({n_pos} must link to a named entry, "
        f"{n_probes - n_pos} must not link). Same probes and verdicts for every variant.",
        "Deeplink accuracy = correct / **WRONG** / abstain. Latency = P95 per action. "
        "Step accuracy is identical across variants (only deeplink mapping changes); "
        "it comes from the manual review.", "",
        "| Architecture Variant | Step Accuracy | Deeplink accuracy (correct / wrong / abstain) | Latency (P95) | Cost / Query | Key Observations |",
        "|---|---|---|---|---|---|",
        row(f"Baseline: Full LLM Deeplink Mapping ({model})", base,
            "whole catalog in the prompt; no confidence signal, so it cannot abstain on weak matches"),
        row(f"Variant A: Hybrid BM25 + Dense (alpha {alpha}, floor {floor}, margin {margin}) — ours", a,
            "calibrated to 0 wrong; abstains when unsure"),
        row("Variant B: Pure Rules-Based (BM25 keywords only, same thresholds)", b,
            "literal word overlap; confuses e.g. 'Font size' with 'Bold font'"),
    ]
    if b_best:
        lines.append(row(f"Variant B tuned (best keyword-only config: floor {b_best['floor']}, margin {b_best['margin']})",
                         b_best, "its best achievable trade-off"))
    return "\n".join(lines) + "\n"
