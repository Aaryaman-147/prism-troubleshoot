#!/usr/bin/env python3
"""
verify_cache_real_model.py  --  BUG-001 + cache-threshold check with the REAL embedding model.

Run from the repo root (the folder that contains app/), with your normal venv active:

    python verify_cache_real_model.py
    python verify_cache_real_model.py --paraphrases my_paraphrases.tsv --probes my_probes.txt

Needs: your normal requirements (sentence-transformers etc.) and internet ONCE so
all-MiniLM-L6-v2 can download (or an already-cached model). No LLM key is needed:
every LLM call is blocked, so a request that gets past the cache simply shows up as
"cache_hit = False" (it would have gone to the cold path).

It does NOT modify the repo. Read-only: it loads app/data/*.json* and starts the app
in-process (FastAPI TestClient), which runs the real startup cache warm-up.

Parts
  0  Preflight      real model sanity check, warm-cache load stats, reference_fp coverage
  A  Pairwise       which of Samsung's 20 visible queries would be served EACH OTHER's plan
                    by the reference-less semantic cache (threshold 0.75 by default)
  B  BUG-001        query_i sent together with SIIS document_j (i != j).
                    Fixed behaviour = ZERO cache hits for a different document.
                    Diagonal (i, i) = does a warmed plan still serve its OWN document?
  C  Probes         status / similarity / matched plan for hand-picked probe phrasings
  D  Sweep          (only with --paraphrases) correct-hit / wrong-hit / miss rate per threshold

--paraphrases file format (UTF-8, tab separated, one per line, '#' comments allowed):
    <warm_id>\t<your own paraphrase of that visible query>
where warm_id is the 1-based line number of the query in app/data/cache_warm.jsonl.
Write them yourself (typos, keyword-only, casual, different device names). Do NOT reuse
the pipeline's own query_variations: those are stored in the cache, so they always hit.
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, str(Path.cwd()))

ap = argparse.ArgumentParser()
ap.add_argument("--paraphrases", help="TSV: warm_id<TAB>paraphrase (see docstring)")
ap.add_argument("--probes", help="text file, one probe query per line")
ap.add_argument("--pair-threshold", type=float, default=0.75, help="listing threshold for Part A")
ap.add_argument("--auto", action="store_true",
                help="Part D without writing paraphrases: mechanical perturbations of the visible queries "
                     "(drop device names, keywords only, typos, first clause)")
ap.add_argument("--emit-template", action="store_true",
                help="write paraphrase_template.tsv (every warmed query as a comment) to fill in for --paraphrases")
ap.add_argument("--report", default="verify_report.txt", help="everything printed is also saved here")
args = ap.parse_args()

class _Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, x):
        for st in self.streams:
            st.write(x)
    def flush(self):
        for st in self.streams:
            st.flush()

_REAL_OUT = sys.stdout
_report_fh = open(args.report, "w", encoding="utf-8")
sys.stdout = _Tee(_REAL_OUT, _report_fh)
import logging                                        # noqa: E402
logging.disable(logging.CRITICAL)                     # the app logs every blocked LLM call as an error


def quiet():
    """Swallow the pipeline's own prints AND tracebacks (the blocked LLM raises inside it, by design)."""
    class _Q(contextlib.ExitStack):
        def __enter__(self):
            super().__enter__()
            self.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.enter_context(contextlib.redirect_stderr(io.StringIO()))
            return self
    return _Q()


if not Path("app/main.py").exists():
    sys.exit("Run this from the repo root (the folder containing app/).")

import numpy as np                                   # noqa: E402
from fastapi.testclient import TestClient            # noqa: E402

import app.main as app_main                          # noqa: E402
from app.core.config import settings, config_fingerprint   # noqa: E402
from app.core.embeddings import embed, cosine_sim    # noqa: E402
from app.cache.semantic_cache import cache, normalize_for_matching, _norm_text   # noqa: E402
from app.pipeline.normalize import reference_fingerprint, normalize_siis   # noqa: E402

# ---- block every LLM call (so no key / no cost / deterministic) --------------------------------
LLM_CALLS = Counter()


class LLMBlocked(Exception):
    pass


def _blocked(*a, **k):
    LLM_CALLS["blocked_calls"] += 1
    raise LLMBlocked("LLM blocked by verify_cache_real_model.py")


async def _blocked_async(*a, **k):
    _blocked()

for mod in list(sys.modules.values()):
    for name in ("generate_json_async", "_generate_openrouter_async"):
        if getattr(mod, name, None) is not None:
            setattr(mod, name, _blocked_async)
    for name in ("generate_json", "_generate_gemini", "_generate_openrouter"):
        if getattr(mod, name, None) is not None:
            setattr(mod, name, _blocked)


def clean_num(q: str) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", q).strip().strip('"')


def title_of(resp: dict) -> str:
    ctx = (resp.get("contexts") or [])
    return ctx[0]["title"] if ctx else f"<no plan: {resp.get('fallback')}>"


def short(s: str, n: int = 78) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def emb(text: str) -> np.ndarray:
    return embed(normalize_for_matching(text))


data = Path("app/data")
siis_rows = json.loads((data / "siis_responses.json").read_text(encoding="utf-8"))["responses"]
warm_path = Path(settings.CACHE_WARM_PATH) if settings.CACHE_WARM_PATH else data / "cache_warm.jsonl"
warm_rows = ([json.loads(l) for l in warm_path.read_text(encoding="utf-8").splitlines() if l.strip()]
             if warm_path.exists() else [])

print("=" * 100)
print("PART 0  PREFLIGHT")
print("=" * 100)
print(f"embedding model setting : {settings.EMBEDDING_MODEL}")
a, b, c = emb("phone screen flickers"), emb("display keeps flickering"), emb("how to bake sourdough bread")
rel, unrel = cosine_sim(a, b), cosine_sim(a, c)
print(f"sanity: related pair {rel:.3f}  vs unrelated pair {unrel:.3f}", end="  ")
if rel < 0.5 or unrel > 0.35:
    print("<-- SUSPICIOUS: this does not look like a real sentence-embedding model!")
else:
    print("(looks like a real model)")
print(f"thresholds              : hit={settings.CACHE_HIT_THRESHOLD}  near_miss={settings.CACHE_NEAR_MISS_THRESHOLD}  "
      f"with_siis={getattr(settings, 'CACHE_HIT_THRESHOLD_WITH_SIIS', 'MISSING (old code!)')}")
print(f"config fingerprint      : {config_fingerprint()}")
print(f"warm file               : {warm_path}  exists={warm_path.exists()}  rows={len(warm_rows)}")
if warm_rows:
    fps = Counter((r.get("meta") or {}).get("config_fingerprint") for r in warm_rows)
    refs = sum(1 for r in warm_rows if (r.get("meta") or {}).get("reference_fp"))
    print(f"warm file fingerprints  : {dict(fps)}   (must equal {config_fingerprint()} or every row is skipped as stale)")
    print(f"rows carrying reference_fp: {refs}/{len(warm_rows)}  (0 => BUG-001 fix cannot recognise their document)")

client_cm = TestClient(app_main.app)
client = client_cm.__enter__()          # runs lifespan: loads model, catalog, warms the cache
try:
    st = app_main._state.get("cache_warm")
    print(f"warm-up result          : {st}")
    clusters = list(cache._clusters.values())
    print(f"clusters in cache       : {len(clusters)}   with reference_fp: {sum(1 for c in clusters if c.reference_fp)}")
    if not clusters:
        print("!! No warmed clusters. Regenerate the warm file with the CURRENT code (batch_run), then re-run.")

    # visible queries + their own SIIS documents
    vis = []
    for r in siis_rows:
        vis.append({"id": r["id"], "q": r["original_query"], "siis": r["siis_response"]})

    # map every visible query to the warm cluster's plan title (cluster found through the exact index)
    def cluster_for(q: str):
        cid = cache._exact.get(_norm_text(q)) or cache._exact.get(_norm_text(clean_num(q)))
        return cache._clusters.get(cid) if cid else None

    def plan_title(cl):
        if cl is None:
            return "<not in cache>"
        ctx = cl.payload.contexts
        if not ctx:
            return "<empty plan>"
        return " + ".join(c.title for c in ctx)          # multi-issue plans show every goal

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print(f"PART A  PAIRWISE SIMILARITY of the {len(vis)} visible queries (reference-less path)")
    print("=" * 100)
    vecs = [emb(clean_num(v["q"])) for v in vis]
    n = len(vis)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((cosine_sim(vecs[i], vecs[j]), i, j))
    pairs.sort(reverse=True)
    for t in (0.70, 0.75, 0.80, 0.85, 0.90):
        print(f"  pairs with similarity >= {t:.2f}: {sum(1 for p in pairs if p[0] >= t)}")
    print(f"\n  Pairs >= {args.pair_threshold:.2f}: each such query would be served the OTHER query's cached plan\n"
          f"  when no siis_response is sent. JUDGE THESE BY EYE: is the plan right for both complaints?\n")
    for s, i, j in [p for p in pairs if p[0] >= args.pair_threshold]:
        print(f"  {s:.3f}  [{vis[i]['id']}] {short(clean_num(vis[i]['q']))}\n"
              f"         [{vis[j]['id']}] {short(clean_num(vis[j]['q']))}\n"
              f"         plans: '{plan_title(cluster_for(vis[i]['q']))}'  vs  '{plan_title(cluster_for(vis[j]['q']))}'")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("PART B  BUG-001  query_i + SIIS document_j through POST /v1/troubleshoot")
    print("=" * 100)
    from app.pipeline.normalize import normalize_siis
    fp = [reference_fingerprint(normalize_siis(v["siis"])) for v in vis]
    same_doc_rows = {}
    for k, f in enumerate(fp):
        same_doc_rows.setdefault(f, []).append(vis[k]["id"])
    shared = {f: ids for f, ids in same_doc_rows.items() if len(ids) > 1}
    print(f"  visible queries that share an identical SIIS document with another query: "
          f"{sum(len(v) for v in shared.values())} (groups: {[v for v in shared.values()]})")
    diag_hit = diag_tot = 0
    diag_miss = []
    guard_fail, sibling_hit, cross_tot = [], [], 0
    for i, vi in enumerate(vis):
        for j, vj in enumerate(vis):
            with quiet():
                r = client.post("/v1/troubleshoot", json={"query": vi["q"], "siis_response": vj["siis"]})
            if r.status_code != 200:
                print(f"  HTTP {r.status_code} for ({vi['id']},{vj['id']}): {r.text[:120]}")
                continue
            body = r.json()
            hit = bool(body["meta"]["cache_hit"])
            if i == j:
                diag_tot += 1
                diag_hit += hit
                if not hit:
                    diag_miss.append((vi["id"], body["meta"].get("cache_similarity"), body["response"].get("fallback")))
            elif fp[i] != fp[j] and hit:
                lk = cache.lookup(vi["q"])                 # same deterministic lookup the pipeline did
                cl_fp = lk.cluster.reference_fp if lk.cluster else None
                rec = (vi, vj, body, lk.cluster.canonical_query if lk.cluster else "?", cl_fp)
                (sibling_hit if cl_fp == fp[j] else guard_fail).append(rec)
            if fp[i] != fp[j]:
                cross_tot += 1
        print(f"  ...query {i+1}/{len(vis)} done", end="\r")
    print()
    print(f"  cross-document requests (different SIIS text): {cross_tot}")
    print(f"  GUARD FAILURES (served a plan grounded in a DIFFERENT document than the one supplied): "
          f"{len(guard_fail)}   -> {'PASS' if not guard_fail else 'FAIL  <-- this is the real BUG-001'}")
    for vi, vj, body, canon, cfp in guard_fail[:15]:
        print(f"     query {vi['id']} + doc {vj['id']} -> '{title_of(body['response'])}' (sim {body['meta'].get('cache_similarity')}) "
              f"cluster='{short(canon, 50)}' cluster_fp={cfp}")
    print(f"  SAME-DOCUMENT SIBLING HITS (allowed by design: supplied doc == cluster's doc AND sim >= "
          f"{settings.CACHE_HIT_THRESHOLD_WITH_SIIS}): {len(sibling_hit)}")
    print("     Judge these by eye: query_i is a DIFFERENT complaint that happens to share a SIIS document with the cached plan.")
    for vi, vj, body, canon, cfp in sibling_hit[:15]:
        print(f"     query {vi['id']} ({short(clean_num(vi['q']), 50)!r}) + doc {vj['id']} -> plan '{title_of(body['response'])}' "
              f"(sim {body['meta'].get('cache_similarity')}), cached for: {short(clean_num(canon), 60)!r}")
    print(f"  own-document requests served from cache: {diag_hit}/{diag_tot}")
    for qid, sim, fb in diag_miss:
        print(f"     own-doc MISS: {qid} (cache_similarity={sim}, fallback={fb})  "
              f"[expected for the queries that had no cluster of their own (skipped_cache_hit); anything else is worth a look]")
    print(f"  LLM calls blocked (= requests that would have gone to the 9-13 s cold path): {LLM_CALLS['blocked_calls']}")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("PART C  PROBES (reference-less lookup: cache.lookup)")
    print("=" * 100)
    probes = [
        # paraphrase / casual
        "my foldable's inner display went completely black", "screen stays dark but the phone still vibrates",
        "tablet display is blank after I turned it on", "half of my phone screen is black",
        # typos / shorthand / keyword-only
        "scren flickers n batt dies fast", "screen black", "display broken lines", "touch not working",
        # other domains
        "battery drains overnight while idle", "camera app crashes when I open it", "phone got slow after the update",
        # ambiguous / multi-issue
        "screen flickers and the battery dies fast",
        # off-domain / junk (should MISS)
        "how do I bake sourdough bread", "asdfghjkl", "what is the capital of France",
    ]
    if args.probes:
        probes += [l.strip() for l in Path(args.probes).read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"  {'status':9} {'sim':>6}  probe  ->  matched plan  (matched cluster's canonical query)")
    for p in probes:
        lk = cache.lookup(p)
        cl = lk.cluster
        print(f"  {lk.status:9} {lk.similarity:6.3f}  {short(p, 46)!r}  ->  "
              f"{plan_title(cl) if cl else '-'}  ({short(cl.canonical_query, 50) if cl else '-'})")

    # ---------------------------------------------------------------------------------------
    if args.emit_template:
        with open("paraphrase_template.tsv", "w", encoding="utf-8") as fh:
            fh.write("# warm_id<TAB>your own paraphrase. Write 2-3 per query. Typos/keyword-only/casual welcome.\n")
            for k, r in enumerate(warm_rows, 1):
                fh.write(f"# {k}: {short(r['query'], 150)}\n")
        print("\nWrote paraphrase_template.tsv (queries listed as comments).")

    def _auto_variants(q: str):
        import random
        q = clean_num(q)
        rnd = random.Random(7)
        no_dev = re.sub(r"\b(TechCorp|Nexa|Fold|Ultra|X1|A1\d\w*|tablet|foldable)\b", "", q, flags=re.I)
        no_dev = re.sub(r"\s+", " ", no_dev).strip()
        stop = set("my the a an is are was were be been to of and or but so that this it its i me can't cant "
                   "when after before with on in at for from as by do does did not no really very just".split())
        kw = " ".join([w for w in re.findall(r"[A-Za-z']+", q) if w.lower() not in stop][:7]).lower()
        words = q.split()
        for idx in rnd.sample(range(len(words)), k=min(2, len(words))):
            w = words[idx]
            if len(w) > 4:
                words[idx] = w[:2] + w[3] + w[2] + w[4:]        # adjacent-letter swap
        typo = " ".join(words).lower()
        first = re.split(r",| and | but |\. ", q)[0]
        return [("no-device-name", no_dev), ("keywords-only", kw), ("typos+lowercase", typo), ("first-clause", first)]

    cases = []
    if args.paraphrases or args.auto:
        print("\n" + "=" * 100)
        print("PART D  THRESHOLD SWEEP" + (" (mechanical perturbations)" if args.auto else " on YOUR paraphrases"))
        print("=" * 100)

        def resolve(key: str):
            key = key.strip()
            if key.isdigit() and 0 < int(key) <= len(warm_rows):
                return cluster_for(warm_rows[int(key) - 1]["query"])
            for r in warm_rows:
                if key.lower() in r["query"].lower():
                    return cluster_for(r["query"])
            return None

        if args.paraphrases:
            for line in Path(args.paraphrases).read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                key, _, text = line.partition("\t")
                exp = resolve(key)
                if exp is None or not text.strip():
                    print(f"  skip (no cluster for {key!r}): {short(text)}")
                    continue
                cases.append((exp, text.strip(), "human"))
        if args.auto:
            seen = set()
            for r in warm_rows[:20]:                       # Samsung's visible queries only
                exp = cluster_for(r["query"])
                if exp is None or id(exp) in seen:
                    continue
                seen.add(id(exp))
                for kind, txt in _auto_variants(r["query"]):
                    if len(txt.split()) >= 2:
                        cases.append((exp, txt, kind))
        print(f"  {len(cases)} test phrasings")
        scored = []
        for exp, text, kind in cases:
            v = emb(text)
            best = max(clusters, key=lambda c: cache._similarity(v, c))
            scored.append((exp, best, cache._similarity(v, best), text, kind))
        print(f"\n  {'thr':>5} {'correct hit':>12} {'WRONG hit':>10} {'miss':>6}")
        for t in (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
            ok = sum(1 for e, b, sc, _, _k in scored if sc >= t and b is e)
            bad = sum(1 for e, b, sc, _, _k in scored if sc >= t and b is not e)
            miss = sum(1 for e, b, sc, _, _k in scored if sc < t)
            m = len(scored) or 1
            print(f"  {t:5.2f} {ok:5d} ({100*ok/m:3.0f}%) {bad:5d} ({100*bad/m:3.0f}%) {miss:3d} ({100*miss/m:3.0f}%)")
        kinds = sorted({k for *_x, k in scored})
        print(f"\n  correct-hit rate at the shipped threshold ({settings.CACHE_HIT_THRESHOLD}) by kind:")
        for k in kinds:
            sub = [x for x in scored if x[4] == k]
            ok = sum(1 for e, b, sc, _, _k in sub if sc >= settings.CACHE_HIT_THRESHOLD and b is e)
            print(f"    {k:16} {ok}/{len(sub)}")
        print("\n  WRONG hits at the shipped hit threshold (a different cached plan would be served):")
        for e, b, sc, text, kind in scored:
            if sc >= settings.CACHE_HIT_THRESHOLD and b is not e:
                print(f"    {sc:.3f} [{kind}] {short(text, 55)!r}: expected '{short(plan_title(e), 30)}', got '{short(plan_title(b), 30)}'")
        print("\n  MISSES at the shipped threshold (would return no_siis_context / go cold):")
        for e, b, sc, text, kind in scored:
            if sc < settings.CACHE_HIT_THRESHOLD:
                print(f"    {sc:.3f} [{kind}] {short(text, 70)!r}")
finally:
    client_cm.__exit__(None, None, None)

print(f"\n(Full output also saved to {args.report})")
print("\nDone. Save this output; the numbers that matter: Part B 'hits on a different document' (must be 0),"
      "\nPart B own-document rate, Part A pairs you judge wrong, and Part D 'WRONG hit' column at 0.75.")
