"""
Tests the pipeline WITH a matching reference text — this is the case that
should actually succeed, unlike a bare query with no siis_response (which
correctly returns no_match per the spec's "No Hallucinated Steps" rule).

Run from anywhere — paths are resolved relative to this file, not your
current working directory:
    python scripts/test_with_reference.py
"""
import json
from pathlib import Path

import httpx

SAMPLES_PATH = Path(__file__).parent.parent / "app" / "data" / "siis_responses_sample.json"

with open(SAMPLES_PATH) as f:
    SAMPLES = json.load(f)

resp = httpx.post(
    "http://localhost:8000/v1/troubleshoot",
    json={
        "query": "screen flickers and the battery dies fast",
        "siis_response": SAMPLES["screen_flicker_battery"],
    },
    timeout=30,
)
print(json.dumps(resp.json(), indent=2))
