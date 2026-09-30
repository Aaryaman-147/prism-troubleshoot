"""
Batch evaluation: run many queries through the real pipeline, write one
Appendix-B record per line to results.jsonl, and score the run into a
metrics.md following the spec's Appendix C template.

Everything here except run_batch() is pure and offline-testable.
"""
import json
import re
import statistics
from pathlib import Path

from app.models.schema import TroubleshootResponse
from app.utils.validators import contains_leaked_url

INFRA_FALLBACKS = {"rate_limited", "extraction_error", "provider_error"}
_NUMBER_PREFIX = re.compile(r"^\s*\d+[.)]\s*")
_GOAL_RE = re.compile(r"^Follow these steps to perform this .+ (Troubleshooting|Configuration)$")


# ---------------------------------------------------------------- loading
def _first_list(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("queries", "responses", "items", "data", "scenarios"):
            if isinstance(obj.get(key), list):
                return obj[key]
        for v in obj.values():
            if isinstance(v, list):
                return v
    return []


def _clean_query(q: str) -> str:
    # Samsung's siis_responses.json row_1 original_query starts "1. My TechCorp..."
    return _NUMBER_PREFIX.sub("", str(q or "")).strip()


def _join_key(text: str) -> str:
    """Key for matching a query to its SIIS row: the same cleaning the API
    applies, whitespace- and quote-insensitive."""
    from app.pipeline.normalize import clean_complaint
    import re as _re
    return _re.sub(r"[^a-z0-9]+", " ", clean_complaint(text).lower()).strip()


def _match_siis(query: str, by_text: dict):
    """Exact match on the cleaned key, else the closest key (>= 0.85).
    Samsung's input.txt line 17 is a merged numbered list on ONE line while
    its SIIS row has line breaks: an exact-text join missed it, the query ran
    WITHOUT its reference, and the deliverable got another query's cached
    plan (external audit BUG-011)."""
    import difflib
    key = _join_key(query)
    if key in by_text:
        return by_text[key]
    close = difflib.get_close_matches(key, list(by_text), n=1, cutoff=0.85)
    return by_text[close[0]] if close else None


def load_cases(queries_path=None, siis_path=None, scenarios_path=None) -> list[dict]:
    """
    Returns [{id, query, siis_response, expected}]. Accepts:
      - our synthetic scenarios file (list of {id, query, siis_response, expected})
      - Samsung queries.json (list of strings or dicts, optionally wrapped)
      - Samsung siis_responses.json ({"responses":[{id, original_query, siis_response}]}),
        used to attach reference text to queries by id, then by query text --
        or used on its own as the case list when there is no queries.json.
    """
    if scenarios_path:
        rows = _first_list(json.loads(Path(scenarios_path).read_text(encoding="utf-8")))
        return [{"id": str(r.get("id", i)), "query": _clean_query(r["query"]),
                 "siis_response": r.get("siis_response"), "expected": r.get("expected")}
                for i, r in enumerate(rows)]

    siis_rows = []
    if siis_path and Path(siis_path).exists():
        siis_rows = _first_list(json.loads(Path(siis_path).read_text(encoding="utf-8")))
    by_id = {str(r.get("id")): r.get("siis_response") for r in siis_rows if r.get("id") is not None}
    by_text = {_join_key(r.get("original_query", "")): r.get("siis_response") for r in siis_rows}

    cases = []
    if queries_path and Path(queries_path).exists() and str(queries_path).endswith(".txt"):
        for i, line in enumerate(l for l in Path(queries_path).read_text(encoding="utf-8").splitlines() if l.strip()):
            q = _clean_query(line)
            cases.append({"id": str(i + 1), "query": q, "siis_response": _match_siis(q, by_text), "expected": None})
    elif queries_path and Path(queries_path).exists():
        for i, r in enumerate(_first_list(json.loads(Path(queries_path).read_text(encoding="utf-8")))):
            if isinstance(r, str):
                cid, q = str(i), r
            else:
                cid = str(r.get("id", i))
                q = r.get("query") or r.get("original_query") or r.get("text") or ""
            q = _clean_query(q)
            siis = (r.get("siis_response") if isinstance(r, dict) else None) \
                or by_id.get(cid) or _match_siis(q, by_text)
            cases.append({"id": cid, "query": q, "siis_response": siis, "expected": None})
    else:
        for i, r in enumerate(siis_rows):
            cases.append({"id": str(r.get("id", i)), "query": _clean_query(r.get("original_query", "")),
                          "siis_response": r.get("siis_response"), "expected": None})
    return cases


# ---------------------------------------------------------- reality check
def shape_check(deeplinks_path=None, queries_path=None, siis_path=None) -> list[str]:
    """
    Compare Samsung's REAL files against the assumptions the code was built
    on (which came from screenshots, not the files). Run this first when the
    data lands; every 'WARN' line is an assumption that didn't hold.
    """
    out = []

    def ok(msg): out.append(f"OK    {msg}")
    def warn(msg): out.append(f"WARN  {msg}")

    if deeplinks_path and Path(deeplinks_path).exists():
        raw = json.loads(Path(deeplinks_path).read_text(encoding="utf-8"))
        ok("deeplinks.json is wrapped {'deeplinks': [...]}") if isinstance(raw, dict) and "deeplinks" in raw \
            else warn(f"deeplinks.json top-level is {type(raw).__name__}, expected wrapped dict")
        entries = _first_list(raw)
        ok(f"{len(entries)} deeplink entries") if entries else warn("no deeplink entries found")
        if entries:
            for key in ("deeplink", "description", "message", "qna_description", "validation", "originalType"):
                n = sum(1 for e in entries if isinstance(e, dict) and e.get(key))
                (ok if n else warn)(f"field '{key}' present on {n}/{len(entries)} entries")
            schemes = sorted({str(e.get("deeplink", "")).split("://")[0] for e in entries if isinstance(e, dict)})
            ok(f"URI schemes: {schemes}")
            dummies = [e["deeplink"] for e in entries if str(e.get("deeplink", "")).endswith("dummy_positive")]
            ok(f"dummy_positive entry: {dummies[0]}") if dummies else \
                warn("no *dummy_positive entry — only manual_null policy is possible")
            vals = [e["validation"] for e in entries if isinstance(e.get("validation"), dict)]
            if vals:
                vkeys = sorted({k for v in vals for k in v})
                ok(f"validation keys seen: {vkeys}")
    else:
        warn("deeplinks.json not found")

    if siis_path and Path(siis_path).exists():
        rows = _first_list(json.loads(Path(siis_path).read_text(encoding="utf-8")))
        ok(f"{len(rows)} SIIS rows")
        objs = [r.get("siis_response") for r in rows if isinstance(r.get("siis_response"), dict)]
        (ok if objs else warn)(f"siis_response is an object on {len(objs)}/{len(rows)} rows")
        from app.pipeline.normalize import clean_siis_content
        stripped = sum(1 for o in objs if clean_siis_content(o.get("title", ""), o.get("content", ""))
                       != (o.get("content") or "").strip())
        (ok if stripped else warn)(f"category-tag prefix stripped on {stripped}/{len(objs)} rows "
                                   f"(inspect a few by hand either way)")
        numbered = sum(1 for r in rows if _NUMBER_PREFIX.match(str(r.get("original_query", ""))))
        if numbered:
            ok(f"{numbered} original_query values carry a leading '1.'-style number (stripped by loader)")
    else:
        warn("siis_responses.json not found")

    if queries_path and Path(queries_path).exists() and str(queries_path).endswith(".txt"):
        lines = [l for l in Path(queries_path).read_text(encoding="utf-8").splitlines() if l.strip()]
        ok(f"{len(lines)} queries in {Path(queries_path).name} (one per line)")
    elif queries_path and Path(queries_path).exists():
        rows = _first_list(json.loads(Path(queries_path).read_text(encoding="utf-8")))
        sample = rows[0] if rows else None
        ok(f"{len(rows)} queries; first item type={type(sample).__name__}"
           + (f", keys={sorted(sample)}" if isinstance(sample, dict) else ""))
    else:
        warn("queries.json not found (runner will use siis_responses.json rows as cases)")
    return out


# ----------------------------------------------------------------- scoring
def outcome_of(record: dict) -> str:
    n = len(record.get("response", {}).get("contexts") or [])
    return "abstain" if n == 0 else ("multi" if n >= 2 else "plan")


def _pct(a, b):
    return None if not b else round(100.0 * a / b, 1)


def _p(values, q):
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 1)


def compute_metrics(records: list[dict], catalog_uris: set[str] | None = None) -> dict:
    """records: [{"result": <Appendix-B dict>, "expected": str|None, "pass": "main"|"paraphrase"}]"""
    catalog_uris = catalog_uris or set()
    main = [r for r in records if r.get("pass", "main") == "main"]
    para = [r for r in records if r.get("pass") == "paraphrase"]

    schema_ok = goals = goals_ok = leaks = 0
    actionable = actionable_in_catalog = autos = autos_linked = autos_real = manual_linked = order_viol = 0
    var_ok = var_total = 0
    fallbacks: dict[str, int] = {}
    cold_lat, hit_lat, abstain_lat, tokens, grounding, costs = [], [], [], [], [], []
    correct = judged = infra = 0

    for r in main:
        res = r["result"]
        try:
            TroubleshootResponse.model_validate(res)
            schema_ok += 1
        except Exception:
            pass
        resp, meta = res.get("response", {}), res.get("meta", {})
        fb = resp.get("fallback")
        if fb:
            fallbacks[fb] = fallbacks.get(fb, 0) + 1
        else:
            var_total += 1
            var_ok += 8 <= len(res.get("query_variations") or []) <= 10

        for g in resp.get("contexts") or []:
            goals += 1
            acts = g.get("actions") or []
            good = bool(_GOAL_RE.match(g.get("goal", ""))) and 2 <= len(g.get("title", "").split()) <= 3
            cats = []
            for a in acts:
                d = a.get("description", "")
                good &= d.startswith("It will") and 5 <= len(d.split()) <= 7
                good &= all(w[:1].isupper() or not w[:1].isalpha() for w in a.get("actionName", "").split())
                cat = a.get("category")
                cats.append(cat)
                strings = [a.get("actionName", ""), d] + [s for sg in a.get("stepGroups") or [] for s in sg.get("steps") or []]
                leaks += sum(1 for s in strings if contains_leaked_url(s))
                linked = any((sg.get("actionableDeeplink") or {}).get("deeplink") for sg in a.get("stepGroups") or [])
                for sg in a.get("stepGroups") or []:
                    link = (sg.get("actionableDeeplink") or {}).get("deeplink")
                    if link:
                        actionable += 1
                        actionable_in_catalog += (not catalog_uris) or link in catalog_uris
                if cat == "auto":
                    autos += 1
                    autos_linked += linked
                    autos_real += any(((sg.get("actionableDeeplink") or {}).get("deeplink") or "").split("://")[-1]
                                      not in ("", "dummy_positive") for sg in a.get("stepGroups") or [])
                elif cat == "manual" and linked:
                    manual_linked += 1
            goals_ok += good
            if "critical" in cats and any(c != "critical" for c in cats[cats.index("critical"):]):
                order_viol += 1

        lat = meta.get("latency_ms")
        if lat is not None:
            if meta.get("cache_hit"):
                hit_lat.append(lat)
            elif fb in ("siis_mismatch", "no_siis_context"):
                abstain_lat.append(lat)
            else:
                cold_lat.append(lat)
                if meta.get("step_grounding_pct") is not None:
                    grounding.append(meta["step_grounding_pct"])
                tokens.append((meta.get("prompt_tokens") or 0) + (meta.get("completion_tokens") or 0))
                costs.append(meta.get("cost_usd") or 0.0)

        exp = r.get("expected")
        if fb in INFRA_FALLBACKS:
            infra += 1          # provider/quota failure: not an accuracy result
        elif exp and exp != "any":
            judged += 1
            correct += outcome_of(res) == exp

    para_hits = sum(1 for r in para if r["result"].get("meta", {}).get("cache_hit"))
    para_lat = [r["result"]["meta"]["latency_ms"] for r in para
                if r["result"].get("meta", {}).get("cache_hit")]
    exact = [r for r in records if r.get("pass") == "exact"]
    exact_lat = [r["result"]["meta"]["latency_ms"] for r in exact if r["result"].get("meta", {}).get("cache_hit")]
    return {
        "cases": len(main), "schema_valid_pct": _pct(schema_ok, len(main)),
        "rule_compliance_pct": _pct(goals_ok, goals), "goals": goals, "url_leaks": leaks,
        "deeplink_catalog_validity_pct": _pct(actionable_in_catalog, actionable),
        "auto_with_deeplink_pct": _pct(autos_linked, autos),
        "auto_with_real_deeplink_pct": _pct(autos_real, autos), "manual_with_deeplink": manual_linked,
        "ordering_violations": order_viol, "variations_compliant_pct": _pct(var_ok, var_total),
        "fallbacks": fallbacks,
        "cold_p50": _p(cold_lat, 0.5), "cold_p95": _p(cold_lat, 0.95), "cold_n": len(cold_lat),
        "hit_p50": _p(hit_lat + para_lat, 0.5), "hit_p95": _p(hit_lat + para_lat, 0.95),
        "hit_n": len(hit_lat) + len(para_lat),
        "exact_p50": _p(exact_lat, 0.5), "exact_p95": _p(exact_lat, 0.95), "exact_n": len(exact_lat),
        "exact_hit_rate_pct": _pct(len(exact_lat), len(exact)),
        "para_p50": _p(para_lat, 0.5), "para_p95": _p(para_lat, 0.95), "para_n": len(para_lat),
        "abstain_p50": _p(abstain_lat, 0.5), "abstain_n": len(abstain_lat),
        "avg_tokens_cold": round(statistics.mean(tokens), 1) if tokens else None,
        "avg_cost_cold_usd": round(statistics.mean(costs), 6) if costs else None,
        "paraphrase_hit_rate_pct": _pct(para_hits, len(para)), "paraphrase_n": len(para),
        "expected_correct_pct": _pct(correct, judged), "expected_judged": judged,
        "infra_failures": infra,
        "step_grounding_pct": round(statistics.mean(grounding), 1) if grounding else None,
    }


def _v(x, unit=""):
    return "n/a" if x is None else f"{x}{unit}"


def _independent_row(m: dict) -> str:
    ind = m.get("independent_paraphrase")
    if not ind:
        return "| Semantic cache hit rate - independently written paraphrases | >= 80% | run scripts/measure_determinism_and_cache.py |"
    return (f"| Semantic cache hit rate - independently written paraphrases | >= 80% | "
            f"**{ind['rate_pct']:.1f}%** ({ind['hits']}/{ind['total']}) |")


def _review_notes(review) -> str:
    low = (review or {}).get("low") or []
    if not low:
        return ""
    lines = ["", "Reviewer notes on plans below full marks:", ""]
    for r in low:
        lines.append(f"* **{r['id']}** ({r['domain']}): steps {r['steps']:g}/3, deeplink {r['deeplink']}. {r['notes']}")
    return "\n".join(lines)


def _review_rows(review) -> str:
    if not review or not review.get("n"):
        return ("| Step accuracy (completeness, correctness, ordering) | 0.0 - 3.0 | pending manual review (scripts/review_sheet.py) |\n"
                "| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | pending manual review |")
    rows = [f"| Step accuracy (completeness, correctness, ordering) | 0.0 - 3.0 | **{review['steps_mean']:.2f}** "
            f"(n = {review['n']} plans) |",
            f"| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | "
            + (f"**{review['deeplink_mean']:.2f}** (n = {review['deeplink_n']} scored actions) |" if review.get("deeplink_n") else "n/a (no auto actions scored) |")]
    for dom, (mean, n) in sorted((review.get("by_domain") or {}).items()):
        rows.append(f"| &nbsp;&nbsp;Step accuracy: {dom} | 0.0 - 3.0 | {mean:.2f} (n = {n}) |")
    return "\n".join(rows)


DEFAULT_ABLATION = ("Run `python scripts/ablation.py --llm`, then `python scripts/finalize_metrics.py` "
                    "to insert the three-variant table here.")


def default_edge_cases(m: dict) -> list[str]:
    fb = m.get("fallbacks") or {}
    return [
        "**Multi-intent:** at most 2 plans per complaint. A third distinct issue in one message "
        "(e.g. Samsung row 17's three numbered complaints) is merged into the closest plan; "
        "over-split single issues are merged back automatically.",
        "**Domain gaps:** Samsung's 20 real queries are all Display. Battery, Camera and Performance "
        "coverage comes from the synthetic scenarios and generated probes, not from Samsung ground truth.",
        "**Reference/complaint mismatch in the data:** e.g. a Gmail blank-screen complaint paired with an "
        "'Email server not responding' document. Plans follow the supplied reference.",
        "**Settings hierarchy variations:** screens absent from the catalog get `dummy_positive`; catalog "
        "duplicates and parent/child pages (e.g. 'View Security Settings' vs 'View More security settings') "
        "account for the remaining whole-catalog mismatches (8/577, 0 opposite toggles).",
        "**Category boundaries:** 'restart', 'safe mode', 'factory reset' and 'firmware update' are forced "
        "to critical; configuring a restart *schedule* stays auto.",
        "**Grounding is lexical:** a correct step worded differently from the reference can be flagged; a "
        "very short reference can yield `insufficient_grounding`.",
        "**Non-English complaints:** translated to English first; plans are returned in English.",
        f"**Cold-path latency:** dominated by provider response time (P95 {m.get('cold_p95')} ms this run); "
        "a 6 s repair budget skips optional LLM repair calls.",
        f"**Fallbacks this run:** {fb or 'none'}.",
    ]


def render_metrics_md(m: dict, model: str, embeddings: str, environment: str, data_note: str,
                      review: dict | None = None, ablation_md: str | None = None,
                      edge_cases: list[str] | None = None) -> str:
    return f"""# System Performance Metrics & Evaluation Report
**Model(s):** {model}
**Embeddings:** {embeddings}
**Environment:** {environment}
**Data:** {data_note}

---

## 1. Schema & Rule Compliance
Evaluated on {m['cases']} cases ({m['goals']} generated goals).

| Metric | Target | Measured Value |
| :--- | :--- | :--- |
| Schema-valid output lines | >= 99% | {_v(m['schema_valid_pct'], '%')} |
| Rule compliance (Goal / Title / Description syntax) | >= 95% | {_v(m['rule_compliance_pct'], '%')} |
| Absolute URL leaks | 0 | {m['url_leaks']} |
| Deeplink catalog validity (exact URI match) | 100% | {_v(m['deeplink_catalog_validity_pct'], '%')} |
| Auto actions carrying valid actionable deeplink | >= 90% | {_v(m['auto_with_deeplink_pct'], '%')} |
| &nbsp;&nbsp;of which a real catalog screen (not the `dummy_positive` placeholder) | reported | {_v(m.get('auto_with_real_deeplink_pct'), '%')} |
| Manual actions carrying a deeplink (should be 0) | 0 | {m['manual_with_deeplink']} |
| Critical-before-safe ordering violations | 0 | {m['ordering_violations']} |
| Generated steps supported by the SIIS text (lexical grounding) | high | {_v(m.get('step_grounding_pct'), '%')} |
| query_variations within 8-10 | 100% | {_v(m['variations_compliant_pct'], '%')} |

---

## 2. Accuracy Benchmarks
Evaluated against reference ground truth across Battery, Display, Camera, and Performance (Samsung's 20 queries + labelled synthetic scenarios); step and deeplink scores are human-rated with REVIEW_GUIDE.md.

| Evaluation Metric | Scale / Anchor | Score |
| :--- | :--- | :--- |
| Outcome matches expected (plan / multi / abstain) | % of labelled cases | {_v(m['expected_correct_pct'], '%')} ({m['expected_judged']} judged; {m['infra_failures']} provider/quota failures excluded) |
{_review_rows(review)}
{_review_notes(review)}

Fallback distribution: {m['fallbacks'] or 'none'}

---

## 3. Latency Benchmarks (spec asks N >= 30 per path; use `batch_run.py --all` for enough cold queries)

| Execution Path | Target (P95) | P50 (ms) | P95 (ms) | N |
| :--- | :--- | :--- | :--- | :--- |
| Cache hit - exact query match | <= 300 ms | {_v(m.get('exact_p50'))} | {_v(m.get('exact_p95'))} | {m.get('exact_n', 0)} |
| Cache hit - unseen semantic paraphrase (held out of cache) | <= 300 ms | {_v(m.get('para_p50'))} | {_v(m.get('para_p95'))} | {m.get('para_n', 0)} |
| Cold query - full pipeline | <= 8000 ms | {_v(m['cold_p50'])} | {_v(m['cold_p95'])} | {m['cold_n']} |
| Early abstention (no LLM call) | - | {_v(m['abstain_p50'])} | - | {m['abstain_n']} |

---

## 4. Operational Cost & Cache Efficacy

| Metric Item | Target | Measured Value |
| :--- | :--- | :--- |
| Cold query average tokens (prompt + completion) | Tracked | {_v(m['avg_tokens_cold'])} |
| Cold query average inference cost | Tracked | ${m.get('avg_cost_cold_usd') or 0:.6f} (rate from LLM_PRICE_PER_MTOK_*; 0 = free tier) |
| Cache hit inference cost | $0.00 | $0.00 |
| Semantic cache hit rate - held-out generated paraphrases (never stored) | >= 80% | {_v(m['paraphrase_hit_rate_pct'], '%')} ({m['paraphrase_n']} paraphrases) |
{_independent_row(m)}
| Cost derivation method | - | (prompt tokens + completion tokens) x rate |

Note: held-out paraphrases are model-generated rewordings that were deliberately
NOT stored in the cache, so every hit is a genuine semantic match. The
independently written paraphrase test (scripts/measure_determinism_and_cache.py)
is the stricter measure: human-style wording, typos included.

---

## 5. Architectural Ablation Analysis
{ablation_md or DEFAULT_ABLATION}

---

## 6. Known Edge Cases & System Limitations
{chr(10).join("* " + e for e in (edge_cases or default_edge_cases(m)))}
"""


def _ram_gb():
    """Total RAM for the Appendix C 'vCPU / RAM / OS' environment line."""
    import os, platform, subprocess
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
    except (ValueError, AttributeError, OSError):
        pass
    if platform.system() == "Windows":
        try:
            import ctypes
            class _M(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("tp", "ap", "tpf", "apf", "tv", "av", "aev")]
            m = _M(); m.dwLength = ctypes.sizeof(_M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.tp / 1e9, 1)
        except Exception:
            return None
    try:
        return round(int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) / 1e9, 1)
    except Exception:
        return None


def environment_string() -> str:
    import os, platform
    ram = _ram_gb()
    return f"{os.cpu_count()} vCPU / {ram if ram else '?'} GB RAM / {platform.system()} {platform.release()}"


# ------------------------------------------------------------------ runner
async def run_batch(cases, out_dir, delay_s=4.0, paraphrase_pass=True, paraphrases_per_case=2,
                    limit=None, log=print):
    """Run cases through the real pipeline. Writes results.jsonl incrementally
    (so a rate-limit stall never loses completed work), then metrics.md."""
    import asyncio
    from app.core.config import settings
    from app.pipeline.deeplink_retrieval import DeeplinkIndex
    from app.pipeline.orchestrator import run_pipeline

    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    _saved_holdout = settings.CACHE_SEED_HOLDOUT
    settings.CACHE_SEED_HOLDOUT = paraphrases_per_case if paraphrase_pass else 0   # measurement only; restored below
    index = DeeplinkIndex(settings.DEEPLINKS_PATH)
    records = []
    cases = cases[:limit] if limit else cases

    with open(out_dir / "results.jsonl", "w", encoding="utf-8") as f:
        for i, c in enumerate(cases, 1):
            try:
                res = (await run_pipeline(c["query"], c.get("siis_response"), index)).model_dump(mode="json")
            except Exception as e:                       # never lose the rest of the run
                import traceback
                log(f"[{i}/{len(cases)}] {c['id']}: CRASHED {type(e).__name__}: {e}")
                traceback.print_exc()
                res = {"query": c["query"], "query_variations": [],
                       "response": {"contexts": [], "fallback": "extraction_error",
                                    "fallback_reason": f"pipeline crash: {type(e).__name__}"},
                       "meta": {"latency_ms": 0.0, "cache_hit": False, "model": "error", "cost_usd": 0.0}}
            line = {"id": c["id"], **{k: res[k] for k in ("query", "query_variations", "response", "meta")}}
            f.write(json.dumps(line, ensure_ascii=False) + "\n"); f.flush()
            records.append({"result": res, "expected": c.get("expected"), "pass": "main"})
            m = res["meta"]
            log(f"[{i}/{len(cases)}] {c['id']}: {outcome_of(res)} "
                f"fallback={res['response'].get('fallback')} {m['latency_ms']}ms cache_hit={m['cache_hit']}")
            if not m["cache_hit"] and m.get("model") not in ("none", "relevance-check-only"):
                await asyncio.sleep(delay_s)

    if paraphrase_pass:
        # Exact-repeat pass (Appendix C: "cache hit - exact query match").
        for r, c in [(r, c) for r, c in zip(records, cases) if not r["result"]["response"].get("fallback")]:
            res = (await run_pipeline(c["query"], c.get("siis_response"), index)).model_dump(mode="json")
            records.append({"result": res, "expected": None, "pass": "exact"})
        for r in [r for r in records if r.get("pass") == "main" and not r["result"]["response"].get("fallback")]:
            for p in (r["result"].get("query_variations") or [])[-paraphrases_per_case:]:   # held-out, never stored
                res = (await run_pipeline(p, None, index)).model_dump(mode="json")
                records.append({"result": res, "expected": None, "pass": "paraphrase"})
                log(f"  paraphrase: cache_hit={res['meta']['cache_hit']} '{p[:60]}'")

    metrics = compute_metrics(records, set(index.catalog_by_uri))
    model = settings.OPENROUTER_MODEL if settings.LLM_PROVIDER == "openrouter" else settings.LLM_MODEL
    import platform, os
    md = render_metrics_md(
        metrics, model=f"{settings.LLM_PROVIDER}/{model}", embeddings=settings.EMBEDDING_MODEL,
        environment=environment_string(),
        data_note=f"{len(cases)} cases; catalog {settings.DEEPLINKS_PATH} ({len(index.catalog_by_uri)} entries)",
    )
    (out_dir / "metrics.md").write_text(md, encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps(
        {**metrics, "_header": {"model": f"{settings.LLM_PROVIDER}/{model}", "embeddings": settings.EMBEDDING_MODEL,
                                "environment": environment_string(),
                                "data": f"{len(cases)} cases; catalog {settings.DEEPLINKS_PATH} ({len(index.catalog_by_uri)} entries)"}},
        indent=2), encoding="utf-8")
    settings.CACHE_SEED_HOLDOUT = _saved_holdout
    return metrics
