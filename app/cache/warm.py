"""
Pre-warm the semantic cache from a results.jsonl produced by
scripts/batch_run.py. Spec: "If siis_response is omitted, the engine performs
semantic lookup against pre-warmed cache entries."

Only successful records are loaded, and only if every deeplink they carry
still exists in the CURRENT catalog -- results produced against an older or
placeholder catalog are skipped as stale rather than served.
"""
import json
from pathlib import Path

from app.models.schema import ContextDeeplinkResponse


def _deeplinks(response: dict):
    for c in response.get("contexts") or []:
        for a in c.get("actions") or []:
            for g in a.get("stepGroups") or []:
                for k in ("actionableDeeplink", "validationDeeplink"):
                    if (g.get(k) or {}).get("deeplink"):
                        yield g[k]["deeplink"]


def warm_cache(path: str, cache, catalog_uris: set[str], validation_uris: set[str] | None = None) -> dict:
    stats = {"loaded": 0, "skipped_fallback": 0, "skipped_stale": 0, "skipped_config": 0, "skipped_cache_hit": 0,
             "skipped_duplicate": 0, "invalid": 0}
    from app.core.config import config_fingerprint
    current = config_fingerprint()
    # Empty/unset path disables warm-up. Path("") is "." -- an existing
    # DIRECTORY -- so a bare exists() check crashed server startup.
    if not path or not Path(path).is_file():
        return stats
    p = Path(path)
    known = set(catalog_uris) | set(validation_uris or ())
    loaded_pairs = set()          # (normalized query, document) already warmed in this run
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            resp = rec["response"]
        except (json.JSONDecodeError, KeyError, TypeError):
            stats["invalid"] += 1; continue
        if resp.get("fallback") or not resp.get("contexts"):
            stats["skipped_fallback"] += 1; continue
        meta = rec.get("meta") or {}
        # A record served FROM cache: older runs recorded neither its document
        # nor config, so it can't be trusted -> skip. Current runs record both,
        # and a hit is only ever for the SAME document, so the query gets its
        # own entry (BUG-010: 5 of Samsung's 20 queries had none).
        if meta.get("cache_hit") and not (meta.get("reference_fp") and meta.get("config_fingerprint")):
            stats["skipped_cache_hit"] += 1; continue
        if any(u not in known for u in _deeplinks(resp)):
            stats["skipped_stale"] += 1; continue
        # Made under different content settings (or before fingerprints
        # existed): would serve plans the current pipeline wouldn't produce.
        if (rec.get("meta") or {}).get("config_fingerprint") != current:
            stats["skipped_config"] += 1; continue
        query = rec.get("query", "")
        ref = meta.get("reference_fp")
        hit = cache.lookup(query)
        # Only a duplicate if the matching cluster is grounded in the SAME
        # document; a sibling complaint's cluster doesn't cover this one.
        pair = (" ".join(query.lower().split()), ref)
        from app.core.config import settings as _s
        served = hit.status == "hit" and hit.cluster.reference_fp == ref and (
            ref is None or hit.similarity >= _s.CACHE_HIT_THRESHOLD_WITH_SIIS)
        # A sibling cluster below the with-reference threshold would NOT be
        # served at evaluation time, so this query needs its own entry
        # (verify_report: rows 15/17/19 had none).
        if pair in loaded_pairs or served:
            stats["skipped_duplicate"] += 1; continue
        try:
            payload = ContextDeeplinkResponse.model_validate(resp)
        except Exception:
            stats["invalid"] += 1; continue
        variations = rec.get("query_variations") or []
        seeds = [query] if len(payload.contexts) > 1 else [query, *variations]   # multi-issue: full complaint only
        cache.insert_new_cluster(query, payload, seed_texts=seeds, variations=variations, reference_fp=ref)
        loaded_pairs.add(pair)
        stats["loaded"] += 1
    return stats
