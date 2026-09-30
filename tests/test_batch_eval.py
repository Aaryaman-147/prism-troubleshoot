"""Offline tests for app/eval/batch.py (loading, reality check, scoring, report)."""
import json
from app.eval.batch import load_cases, shape_check, compute_metrics, render_metrics_md, outcome_of

GOOD = {
    "query": "screen flickers",
    "query_variations": [f"p{i}" for i in range(8)],
    "response": {"contexts": [{
        "goal": "Follow these steps to perform this Display Troubleshooting",
        "title": "Screen flicker", "score": 0.9,
        "actions": [
            {"actionName": "Motion Smoothness", "description": "It will stop the screen flicker",
             "category": "auto", "stepGroups": [{"steps": ["Open Settings"],
              "actionableDeeplink": {"deeplink": "voiceassist://masked/act/a", "description": "d", "message": "m"}}]},
            {"actionName": "Factory Reset", "description": "It will restore every default setting",
             "category": "critical", "stepGroups": [{"steps": ["Open Settings"]}]},
        ]}], "fallback": None},
    "meta": {"latency_ms": 5000.0, "cache_hit": False, "model": "m", "cost_usd": 0.0,
             "prompt_tokens": 100, "completion_tokens": 50},
}
ABSTAIN = {"query": "x", "query_variations": [],
           "response": {"contexts": [], "fallback": "siis_mismatch", "fallback_reason": "r"},
           "meta": {"latency_ms": 20.0, "cache_hit": False, "model": "relevance-check-only", "cost_usd": 0.0}}
HIT = {**GOOD, "meta": {"latency_ms": 12.0, "cache_hit": True, "model": "cache", "cost_usd": 0.0}}


def test_outcome_classification():
    assert outcome_of(GOOD) == "plan" and outcome_of(ABSTAIN) == "abstain"


def test_metrics_on_clean_run():
    m = compute_metrics([
        {"result": GOOD, "expected": "plan", "pass": "main"},
        {"result": ABSTAIN, "expected": "abstain", "pass": "main"},
        {"result": HIT, "expected": None, "pass": "paraphrase"},
    ], {"voiceassist://masked/act/a"})
    assert m["schema_valid_pct"] == 100.0 and m["rule_compliance_pct"] == 100.0
    assert m["url_leaks"] == 0 and m["deeplink_catalog_validity_pct"] == 100.0
    assert m["auto_with_deeplink_pct"] == 100.0 and m["ordering_violations"] == 0
    assert m["expected_correct_pct"] == 100.0 and m["paraphrase_hit_rate_pct"] == 100.0
    assert m["fallbacks"] == {"siis_mismatch": 1} and m["abstain_n"] == 1


def test_metrics_catch_violations():
    bad = json.loads(json.dumps(GOOD))
    acts = bad["response"]["contexts"][0]["actions"]
    acts.reverse()                                          # critical first
    acts[1]["stepGroups"][0]["actionableDeeplink"]["deeplink"] = "voiceassist://invented"
    acts[1]["description"] = "Visit https://example.com now"  # leak + bad description
    m = compute_metrics([{"result": bad, "expected": "abstain", "pass": "main"}], {"voiceassist://masked/act/a"})
    assert m["ordering_violations"] == 1 and m["url_leaks"] == 1
    assert m["deeplink_catalog_validity_pct"] == 0.0 and m["rule_compliance_pct"] == 0.0
    assert m["expected_correct_pct"] == 0.0


def test_report_renders_appendix_c_sections():
    md = render_metrics_md(compute_metrics([{"result": GOOD, "expected": None, "pass": "main"}]),
                           "m", "e", "env", "d")
    for h in ("Schema & Rule Compliance", "Accuracy Benchmarks", "Latency Benchmarks",
              "Operational Cost & Cache Efficacy", "Known Edge Cases"):
        assert h in md


def test_load_samsung_shapes_and_join(tmp_path):
    siis = tmp_path / "siis.json"
    siis.write_text(json.dumps({"_readme": "r", "count": 1, "responses": [
        {"id": "row_1", "original_query": "1. My screen flickers", "siis_response": {"title": "t", "content": "c"}}]}))
    # no queries.json -> SIIS rows become the cases; leading "1." stripped
    cases = load_cases(queries_path=tmp_path / "missing.json", siis_path=siis)
    assert cases == [{"id": "row_1", "query": "My screen flickers",
                      "siis_response": {"title": "t", "content": "c"}, "expected": None}]
    q = tmp_path / "queries.json"
    q.write_text(json.dumps({"queries": [{"id": "row_1", "query": "My screen flickers"}]}))
    assert load_cases(queries_path=q, siis_path=siis)[0]["siis_response"] == {"title": "t", "content": "c"}


def test_synthetic_scenarios_file_loads():
    from pathlib import Path
    cases = load_cases(scenarios_path=Path("scripts/synthetic_scenarios.json"))
    assert len(cases) == 39 and all(c["siis_response"] for c in cases)


def test_shape_check_flags_assumption_breaks(tmp_path):
    dl = tmp_path / "dl.json"
    dl.write_text(json.dumps([{"deeplink": "voiceassist://masked/act/a", "description": "d"}]))
    report = "\n".join(shape_check(dl, None, None))
    assert "WARN  deeplinks.json top-level is list" in report
    assert "WARN  no *dummy_positive entry" in report


def test_run_batch_end_to_end_writes_results_and_metrics(tmp_path):
    """Full runner with mocked LLM + embeddings: proves results.jsonl is one
    valid Appendix-B record per line and metrics.md is produced."""
    import asyncio
    import numpy as np
    from unittest.mock import patch
    from app.core.llm_client import TokenUsage
    from app.eval.batch import run_batch

    cat = tmp_path / "dl.json"
    cat.write_text(json.dumps({"deeplinks": [{"deeplink": "voiceassist://masked/act/a",
                                              "description": "Opens display settings"}]}))
    extraction = {"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting",
                                "title": "Screen flicker", "score": 0.9,
                                "actions": [{"actionName": "Motion Smoothness",
                                             "description": "It will stop the screen flicker",
                                             "category": "manual", "stepGroups": [{"steps": ["Open Settings"]}]}]}]}

    async def enrich(q):
        return {"canonical_query": q, "query_variations": [f"{q} v{i}" for i in range(8)]}, TokenUsage(10, 20)

    async def extract(q, r, sub_issues=None):
        return extraction, TokenUsage(30, 40)

    # Abstention case first: the mock embeds every text identically, so any
    # case run after c1 would be a cache hit on c1's plan.
    cases = [{"id": "c2", "query": "phone hot", "siis_response": None, "expected": "abstain"},
             {"id": "c1", "query": "screen flickers", "siis_response": "Display flicker fix text", "expected": "plan"}]
    vec = np.array([1.0, 0.0])
    from app.core.config import settings
    with patch.object(settings, "DEEPLINKS_PATH", str(cat)), \
         patch("app.pipeline.deeplink_retrieval.embed_batch", return_value=np.array([vec])), \
         patch("app.pipeline.deeplink_retrieval.embed", return_value=vec), \
         patch("app.pipeline.relevance.embed", return_value=vec), \
         patch("app.cache.semantic_cache.embed", return_value=vec), \
         patch("app.pipeline.orchestrator.enrich_query_async", side_effect=enrich), \
         patch("app.pipeline.orchestrator.extract_structure_async", side_effect=extract), \
         patch("app.pipeline.orchestrator.cache", __import__("app.cache.semantic_cache", fromlist=["x"]).SemanticCache()):
        m = asyncio.run(run_batch(cases, tmp_path / "out", delay_s=0, log=lambda *_: None))

    lines = (tmp_path / "out" / "results.jsonl").read_text().splitlines()
    assert len(lines) == 2
    for ln in lines:
        rec = json.loads(ln)
        assert {"query", "query_variations", "response", "meta"} <= set(rec)
    assert (tmp_path / "out" / "metrics.md").exists()
    assert m["expected_correct_pct"] == 100.0 and m["paraphrase_hit_rate_pct"] == 100.0


APPENDIX_C_LINES = [
    "# System Performance Metrics & Evaluation Report", "**Model(s):**", "**Embeddings:**", "**Environment:**",
    "## 1. Schema & Rule Compliance", "Schema-valid output lines", "Rule compliance (Goal / Title / Description syntax)",
    "Absolute URL leaks", "Deeplink catalog validity (exact URI match)", "Auto actions carrying valid actionable deeplink",
    "## 2. Accuracy Benchmarks", "Battery, Display, Camera, and Performance",
    "Step accuracy (completeness, correctness, ordering)", "Deeplink relevance (exact target screen vs. parent menu)",
    "## 3. Latency Benchmarks", "Cache hit - exact query match", "Cache hit - unseen semantic paraphrase",
    "Cold query - full pipeline", "## 4. Operational Cost & Cache Efficacy", "Cold query average inference cost",
    "Cache hit inference cost", "Semantic cache hit rate", "(prompt tokens + completion tokens) x rate",
    "## 5. Architectural Ablation Analysis", "## 6. Known Edge Cases & System Limitations",
]


def test_metrics_md_follows_appendix_c_template_row_by_row():
    md = render_metrics_md(compute_metrics([{"result": GOOD, "expected": None, "pass": "main"}]),
                           "m", "e", "8 vCPU / 16.0 GB RAM / Windows 11", "d")
    missing = [l for l in APPENDIX_C_LINES if l not in md]
    assert not missing, missing
    assert "GB RAM" in md
    assert "multi-intent" in md.lower() and "domain gaps" in md.lower() and "hierarchy" in md.lower()   # section 6 filled
    assert "Fill in from" not in md


def test_manual_scores_flow_into_section_2(tmp_path):
    from app.eval.review import load_scores, scores_template, domain_of
    p = tmp_path / "results.jsonl"
    p.write_text("\n".join(json.dumps({**GOOD, "id": i, "query": q}) for i, q in
                           [("1", "screen flickers"), ("S1", "battery drains fast"), ("S2", "camera app crashes")]))
    tmpl = scores_template(p)
    assert tmpl.splitlines()[0].startswith("id,domain,steps_0_3")
    assert [domain_of(q) for q in ("screen flickers", "battery drains fast", "camera app crashes")] == ["Display", "Battery", "Camera"]
    filled = tmp_path / "scores.csv"
    filled.write_text("id,domain,steps_0_3,deeplink_0_2_or_na,notes,query\n1,Display,3,2,,q\nS1,Battery,2,n/a,,q\nS2,Camera,1,1,,q\n")
    r = load_scores(filled)
    assert r["n"] == 3 and r["steps_mean"] == 2.0 and r["deeplink_n"] == 2 and r["deeplink_mean"] == 1.5
    md = render_metrics_md(compute_metrics([{"result": GOOD, "expected": None, "pass": "main"}]), "m", "e", "env", "d", review=r)
    assert "**2.00** (n = 3 plans)" in md and "Step accuracy: Battery" in md


def test_finalize_assembles_full_report(tmp_path, monkeypatch):
    import subprocess, sys, os
    res = tmp_path / "results"; res.mkdir()
    m = compute_metrics([{"result": GOOD, "expected": None, "pass": "main"}])
    m["_header"] = {"model": "nvidia/nemotron", "embeddings": "all-MiniLM-L6-v2", "environment": "8 vCPU / 16 GB RAM / Windows", "data": "59 cases"}
    (res / "metrics.json").write_text(json.dumps(m))
    (res / "ablation_results.md").write_text("# x\n\n| Architecture Variant | Step Accuracy |\n|---|---|\n| Baseline: Full LLM Deeplink Mapping | same |\n")
    (res / "manual_scores.csv").write_text("id,domain,steps_0_3,deeplink_0_2_or_na,notes,query\n1,Display,3,2,,q\n")
    script = os.path.join(os.getcwd(), "scripts", "finalize_metrics.py")
    env = {**os.environ, "PYTHONPATH": os.getcwd() + os.pathsep + os.environ.get("PYTHONPATH", ""), "PRISM_NO_DOTENV": "1"}
    subprocess.run([sys.executable, script], cwd=tmp_path, env=env, check=True, capture_output=True, text=True)
    md = (res / "metrics.md").read_text()
    assert "Baseline: Full LLM Deeplink Mapping" in md and "**3.00** (n = 1 plans)" in md and "nvidia/nemotron" in md


def test_ram_is_reported():
    from app.eval.batch import environment_string
    assert "vCPU" in environment_string() and "GB RAM" in environment_string()
