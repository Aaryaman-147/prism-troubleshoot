"""Build a human review sheet: each plan beside its SIIS reference, with each
step's source sentence, and blanks for step (0-3) and deeplink (0-2) scores."""
import json
from pathlib import Path

from app.eval.batch import _clean_query, _first_list
from app.pipeline.grounding import step_sources
from app.pipeline.normalize import normalize_siis


def load_references(siis_path=None, scenarios_path=None) -> dict:
    refs = {}
    if siis_path and Path(siis_path).exists():
        for r in _first_list(json.loads(Path(siis_path).read_text(encoding="utf-8"))):
            refs[str(r.get("id"))] = r.get("siis_response")
            refs[_clean_query(r.get("original_query", "")).lower()] = r.get("siis_response")
    if scenarios_path and Path(scenarios_path).exists():
        for r in _first_list(json.loads(Path(scenarios_path).read_text(encoding="utf-8"))):
            refs[str(r.get("id"))] = r.get("siis_response")
    return refs


def build_sheet(results_path, refs: dict, limit: int | None = None) -> str:
    lines = ["# Manual review sheet", "",
             "Score each plan against its reference. **Steps** 0-3: 3 = complete, correct, well ordered; "
             "0 = wrong or invented. **Deeplink** 0-2: 2 = exact target screen, 1 = parent menu, 0 = wrong. "
             "Copy totals into TESTING.md's manual review table.", ""]
    rows = [json.loads(l) for l in Path(results_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    shown = 0
    for r in rows:
        ctx = r["response"].get("contexts") or []
        if not ctx or r["meta"].get("cache_hit"):
            continue
        ref = refs.get(str(r.get("id"))) or refs.get(_clean_query(r["query"]).lower())
        ref_text = normalize_siis(ref) if ref else ""
        title = ref.get("title") if isinstance(ref, dict) else (ref or "")[:80]
        sources = step_sources(ctx, ref_text) if ref_text else {}
        lines += [f"## {r.get('id', '?')}: {r['query']}", "", f"**Reference:** {title or '(none found)'}", ""]
        for g in ctx:
            lines += [f"### {g['title']} (score {g.get('score')})", ""]
            for a in g["actions"]:
                link = next(((sg.get("actionableDeeplink") or {}) for sg in a["stepGroups"] if sg.get("actionableDeeplink")), {})
                lines.append(f"- **{a['actionName']}** [{a.get('category')}] — {a['description']}"
                             + (f"  \n  deeplink: {link.get('message') or link.get('description')}" if link else "  \n  deeplink: none"))
                steps = [s for sg in a["stepGroups"] for s in sg["steps"]]
                srcs = sources.get(a["actionName"], [None] * len(steps))
                for s, src in zip(steps, srcs):
                    lines.append(f"  1. {s}" + (f"  \n     _source: {src}_" if src else "  \n     **_no matching sentence in reference_**"))
            lines.append("")
        lines += ["| Steps (0-3) | Deeplink (0-2) | Notes |", "|---|---|---|", "|  |  |  |", ""]
        shown += 1
        if limit and shown >= limit:
            break
    return "\n".join(lines)


_DOMAINS = [("Battery", ("battery", "charg", "drain", "power saving", "overheat", "hot")),
            ("Camera", ("camera", "photo", "picture", "video", "lens")),
            ("Performance", ("slow", "lag", "restart", "reboot", "freez", "crash", "delay", "memory", "storage", "overheat")),
            ("Display", ("screen", "display", "flicker", "blank", "black", "bright", "touch", "rotation"))]


def domain_of(query: str) -> str:
    q = (query or "").lower()
    for name, keys in _DOMAINS:
        if any(k in q for k in keys):
            return name
    return "Other"


def scores_template(results_path, limit=None) -> str:
    """CSV to fill during manual review: one row per plan; deeplink may be n/a."""
    import csv, io
    rows = [json.loads(l) for l in Path(results_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["id", "domain", "steps_0_3", "deeplink_0_2_or_na", "notes", "query"])
    n = 0
    for r in rows:
        if not (r["response"].get("contexts")) or r["meta"].get("cache_hit"):
            continue
        w.writerow([r.get("id", ""), domain_of(r["query"]), "", "", "", r["query"][:120]])
        n += 1
        if limit and n >= limit:
            break
    return buf.getvalue()


def load_scores(csv_path) -> dict:
    """Aggregate filled-in scores for Appendix C section 2."""
    import csv
    steps, links, by_dom, low = [], [], {}, []
    # utf-8-sig: Excel saves a byte-order mark, which otherwise renames the
    # first column to "\ufeffid".
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            s = (row.get("steps_0_3") or "").strip()
            if not s:
                continue
            steps.append(float(s))
            by_dom.setdefault(row.get("domain") or "Other", []).append(float(s))
            d = (row.get("deeplink_0_2_or_na") or "").strip().lower()
            if d and d != "n/a" and d != "na":
                links.append(float(d))
            if float(s) < 3 or (d not in ("", "n/a", "na") and float(d) < 2):
                low.append({"id": row.get("id", "?"), "domain": row.get("domain", "?"), "steps": float(s),
                            "deeplink": d or "n/a", "notes": (row.get("notes") or "").strip()})
    return {"n": len(steps), "steps_mean": sum(steps) / len(steps) if steps else 0.0,
            "deeplink_n": len(links), "deeplink_mean": sum(links) / len(links) if links else 0.0,
            "by_domain": {k: (sum(v) / len(v), len(v)) for k, v in by_dom.items()}, "low": low}
