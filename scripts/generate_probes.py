"""
Generate labelled retrieval probes across the whole catalog (uses ~1 LLM call
per 10 probes; 100 probes ~= 10 calls).

  python scripts\\generate_probes.py --n 100
  python scripts\\calibrate_retrieval.py --probes all --detail

Writes app/data/retrieval_eval_generated.json. Review a handful by eye: a
probe whose wording could fairly mean a different setting is a bad probe,
delete it rather than let it distort the numbers.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings
from app.core.llm_client import generate_json
from app.eval.probegen import build_prompt, parse_probes, sample_entries

OUT = Path("app/data/retrieval_eval_generated.json")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=100); ap.add_argument("--delay", type=float, default=2)
    a = ap.parse_args()
    catalog = json.loads(Path(settings.DEEPLINKS_PATH).read_text(encoding="utf-8"))["deeplinks"]
    entries = sample_entries(catalog, a.n)
    probes = []
    for i in range(0, len(entries), 10):
        batch = entries[i:i + 10]
        try:
            data, _ = generate_json(build_prompt(batch), max_output_tokens=2000, required_keys=("probes",))
            got = parse_probes(data, batch)
            probes += got
            print(f"batch {i // 10 + 1}: {len(got)}/{len(batch)} probes")
        except Exception as e:
            print(f"batch {i // 10 + 1} failed: {type(e).__name__}: {e}")
        time.sleep(a.delay)
    OUT.write_text(json.dumps({"_readme": "LLM-written probes; label = source catalog entry. Delete ambiguous ones.",
                               "probes": probes}, indent=1), encoding="utf-8")
    print(f"Wrote {len(probes)} probes to {OUT}")


if __name__ == "__main__":
    main()
