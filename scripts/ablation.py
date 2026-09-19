"""
Ablation study harness — the experiment the deliverables checklist asks for.

Two studies:

  1. RETRIEVAL: hybrid (BM25 + dense) vs dense-only vs BM25-only deeplink
     matching, swept over alpha, plus the effect of the confidence floor and
     the ambiguity margin.

  2. ORDERING: rule-based (category sort) vs LLM-based action ordering.

Run:
    python scripts/ablation.py                      # retrieval only (free, offline)
    python scripts/ablation.py --ordering rule      # + rule-based ordering (free)
    python scripts/ablation.py --ordering both      # + LLM ordering (SPENDS QUOTA)
    python scripts/ablation.py --out results.md     # also write a markdown report

Quota warning: --ordering both makes one LLM call per ordering case (8 by
default). On Gemini's ~20/day free tier that is a meaningful chunk of a day's
budget, so it is opt-in and never runs by default.

METRICS, and why these ones:

  accuracy      — correct decisions over all cases, where abstaining on a
                  case whose expected_deeplink is null counts as CORRECT.
                  This is the headline number.

  wrong_rate    — attached a deeplink, and it was the wrong one. This is the
                  metric that actually matters for the demo and for the
                  spec's screen-resolution scoring: a wrong deeplink sends a
                  user to the wrong settings screen while looking confident.
                  A config with lower accuracy but a much lower wrong_rate is
                  usually the better config.

  abstain_rate  — attached nothing. Split into justified (expected null) and
                  over-abstention (a correct answer existed and was refused).
                  Over-abstention is the cost you pay for a low wrong_rate.

  coverage      — fraction of answerable cases that got a deeplink at all.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.pipeline.deeplink_retrieval import DeeplinkIndex  # noqa: E402
from app.pipeline.ordering import order_actions  # noqa: E402
from app.core.config import settings  # noqa: E402

EVAL_PATH = ROOT / "app" / "data" / "ablation_eval.json"
CATALOG_PATH = ROOT / settings.DEEPLINKS_PATH


# ---------------------------------------------------------------------------
# Retrieval study
# ---------------------------------------------------------------------------

def match_text(case: dict, use_description: bool) -> str:
    """
    Mirrors app/pipeline/ordering._match_text, but with the description
    inclusion toggleable — because "does including the benefit description
    hurt retrieval?" is itself one of the ablations worth reporting. It is the
    change that fixed the wrong-battery-deeplink bug, so it deserves a number
    rather than an assertion.
    """
    name = case["actionName"]
    if use_description:
        return f"{name} {case['description']}"
    return " ".join([name, name, *case["steps"]]).strip()


def run_retrieval_config(
    cases: list[dict],
    alpha: float,
    min_confidence: float,
    margin: float,
    use_description: bool,
) -> dict:
    index = DeeplinkIndex(str(CATALOG_PATH), alpha=alpha)

    correct = wrong = abstained_justified = abstained_over = 0
    attached_answerable = 0
    failures = []

    for case in cases:
        expected = case["expected_deeplink"]
        results = index.search(match_text(case, use_description), top_k=2)

        predicted = None
        if results:
            entry, score = results[0]
            passes_floor = score >= min_confidence
            unambiguous = len(results) < 2 or (score - results[1][1]) >= margin
            if passes_floor and unambiguous:
                predicted = entry.deeplink

        if predicted is None:
            if expected is None:
                correct += 1
                abstained_justified += 1
            else:
                abstained_over += 1
                failures.append((case["id"], "over-abstained", expected, None))
        elif predicted == expected:
            correct += 1
            attached_answerable += 1
        else:
            wrong += 1
            if expected is not None:
                attached_answerable += 1
            failures.append((case["id"], "wrong", expected, predicted))

    n = len(cases)
    answerable = sum(1 for c in cases if c["expected_deeplink"] is not None)

    return {
        "alpha": alpha,
        "min_confidence": min_confidence,
        "margin": margin,
        "use_description": use_description,
        "accuracy": correct / n,
        "wrong_rate": wrong / n,
        "over_abstain_rate": abstained_over / n,
        # Coverage is over ANSWERABLE cases only — attaching a deeplink to a
        # case that should have abstained is not coverage, it is a wrong answer.
        "coverage": (attached_answerable / answerable) if answerable else 0.0,
        "failures": failures,
    }


def retrieval_study(cases: list[dict]) -> list[dict]:
    results = []

    # Study A: the headline ablation — hybrid vs dense-only vs BM25-only.
    for alpha in [0.0, 0.25, 0.5, 0.75, 1.0]:
        results.append(
            run_retrieval_config(
                cases, alpha,
                settings.DEEPLINK_MIN_CONFIDENCE,
                settings.DEEPLINK_MARGIN,
                use_description=False,
            )
        )

    # Study B: does the confidence floor / ambiguity margin earn its keep?
    for min_conf, margin in [(0.0, 0.0), (0.35, 0.0), (0.35, 0.05), (0.5, 0.05), (0.5, 0.1)]:
        results.append(
            run_retrieval_config(cases, 0.5, min_conf, margin, use_description=False)
        )

    # Study C: description-in-query (the old behaviour) vs steps-in-query.
    for use_desc in [True, False]:
        results.append(
            run_retrieval_config(
                cases, 0.5,
                settings.DEEPLINK_MIN_CONFIDENCE,
                settings.DEEPLINK_MARGIN,
                use_description=use_desc,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Ordering study
# ---------------------------------------------------------------------------

ORDERING_PROMPT = """You are ordering troubleshooting actions for a device \
support flow.

Order them from least disruptive to most disruptive: settings changes the \
system can perform safely first, physical actions the user must do next, and \
destructive or irreversible actions (anything that erases data or resets the \
device) LAST.

Actions:
{actions}

Return ONLY valid JSON, no markdown fences, no preamble:
{{"order": ["<actionName>", "<actionName>", ...]}}"""


def order_actions_llm(actions: list[dict]) -> list[dict]:
    """
    LLM-based ordering, for the ablation only. Deliberately NOT wired into the
    pipeline — the point of the study is to find out whether it would be an
    improvement, and the answer should decide that, not the other way round.
    """
    from app.core.llm_client import generate_json

    listing = "\n".join(
        f"- {a['actionName']} (category: {a['category']})" for a in actions
    )
    raw = generate_json(ORDERING_PROMPT.format(actions=listing), max_output_tokens=500)
    order = raw.get("order", [])

    by_name = {a["actionName"]: a for a in actions}
    ordered = [by_name[name] for name in order if name in by_name]
    # Any action the LLM dropped is appended, so a forgetful model is scored
    # on ordering quality rather than silently losing a step.
    ordered += [a for a in actions if a["actionName"] not in order]
    return ordered


CRITICAL_LAST_NOTE = (
    "critical_violations counts cases where a destructive action was placed "
    "before a non-destructive one. This is a SAFETY metric, not a quality "
    "metric — one violation means the system told a user to factory reset "
    "before trying a settings toggle."
)


def run_ordering_config(cases: list[dict], orderer, label: str) -> dict:
    exact = 0
    violations = 0
    errors = 0
    failures = []

    for case in cases:
        try:
            result = orderer([dict(a) for a in case["actions"]])
        except Exception as e:  # an unusable ordering is a result, not a crash
            errors += 1
            failures.append((case["id"], f"error: {type(e).__name__}: {e}"))
            continue

        names = [a["actionName"] for a in result]
        if names == case["expected_order"]:
            exact += 1
        else:
            failures.append((case["id"], f"got {names}"))

        cats = [a.get("category", "manual") for a in result]
        seen_critical = False
        for c in cats:
            if c == "critical":
                seen_critical = True
            elif seen_critical:
                violations += 1
                break

    n = len(cases)
    return {
        "label": label,
        "exact_match": exact / n,
        "critical_violations": violations,
        "errors": errors,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def fmt_retrieval_table(rows: list[dict]) -> str:
    out = [
        "| alpha | min_conf | margin | query text | accuracy | wrong | over-abstain | coverage |",
        "|------:|---------:|-------:|------------|---------:|------:|-------------:|---------:|",
    ]
    for r in rows:
        qt = "name+desc" if r["use_description"] else "name+steps"
        out.append(
            f"| {r['alpha']:.2f} | {r['min_confidence']:.2f} | {r['margin']:.2f} | {qt} "
            f"| {r['accuracy']:.1%} | {r['wrong_rate']:.1%} "
            f"| {r['over_abstain_rate']:.1%} | {r['coverage']:.1%} |"
        )
    return "\n".join(out)


def fmt_ordering_table(rows: list[dict]) -> str:
    out = [
        "| method | exact order match | critical-last violations | errors |",
        "|--------|------------------:|-------------------------:|-------:|",
    ]
    for r in rows:
        out.append(
            f"| {r['label']} | {r['exact_match']:.1%} | {r['critical_violations']} | {r['errors']} |"
        )
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ordering", choices=["none", "rule", "both"], default="rule",
        help="'both' makes real LLM calls and spends free-tier quota.",
    )
    parser.add_argument("--out", type=str, default=None, help="write a markdown report here")
    parser.add_argument(
        "--detail", type=str, default=None,
        help="show per-case top-2 matches for one retrieval case id, under "
             "both name+desc and name+steps, e.g. --detail r07_motion_smoothness",
    )
    args = parser.parse_args()

    if args.detail:
        with open(EVAL_PATH) as f:
            eval_data = json.load(f)
        case = next(
            (c for c in eval_data["retrieval_cases"] if c["id"] == args.detail), None
        )
        if case is None:
            print(f"No case '{args.detail}' in {EVAL_PATH}", file=sys.stderr)
            sys.exit(1)
        index = DeeplinkIndex(str(CATALOG_PATH), alpha=settings.DEEPLINK_ALPHA)
        print(f"case: {case['id']}  expected: {case['expected_deeplink']}\n")
        for use_desc, label in [(True, "name+desc (old)"), (False, "name+steps (new)")]:
            text = match_text(case, use_desc)
            print(f"[{label}] query text: {text!r}")
            for entry, score in index.search(text, top_k=3):
                mark = " <-- top" if score == index.search(text, top_k=1)[0][1] else ""
                print(f"    {score:.4f}  {entry.deeplink}{mark}")
            print()
        return

    with open(EVAL_PATH) as f:
        data = json.load(f)

    sections = []
    sections.append(
        "# Ablation study — Smart Guided Troubleshooting Engine\n\n"
        f"Catalog: `{CATALOG_PATH.name}` "
        f"({len(json.load(open(CATALOG_PATH)))} entries)  \n"
        f"Eval set: {len(data['retrieval_cases'])} retrieval cases, "
        f"{len(data['ordering_cases'])} ordering cases\n"
    )

    catalog_size = len(json.load(open(CATALOG_PATH)))
    if catalog_size < 50:
        sections.append(
            "> **Placeholder-data warning.** These numbers were produced against a\n"
            f"> {catalog_size}-entry placeholder catalog. They are valid for comparing\n"
            "> configurations against each other, and NOT valid as absolute accuracy\n"
            "> claims. Re-run once the real deeplink catalog is in `app/data/`.\n"
        )

    print("Running retrieval study...", file=sys.stderr)
    retrieval_rows = retrieval_study(data["retrieval_cases"])
    sections.append("## 1. Deeplink retrieval\n\n" + fmt_retrieval_table(retrieval_rows))

    worst = max(retrieval_rows, key=lambda r: r["wrong_rate"])
    if worst["failures"]:
        lines = [
            f"- `{cid}` — {kind}: expected `{exp}`, got `{got}`"
            for cid, kind, exp, got in worst["failures"][:8]
        ]
        sections.append(
            "### Failure cases for the worst config by wrong-rate\n\n"
            f"(alpha={worst['alpha']}, min_conf={worst['min_confidence']}, "
            f"margin={worst['margin']}, "
            f"{'name+desc' if worst['use_description'] else 'name+steps'})\n\n"
            + "\n".join(lines)
        )

    if args.ordering != "none":
        print("Running ordering study...", file=sys.stderr)
        ordering_rows = [
            run_ordering_config(data["ordering_cases"], order_actions, "rule-based")
        ]
        if args.ordering == "both":
            print("  (making real LLM calls)", file=sys.stderr)
            ordering_rows.append(
                run_ordering_config(data["ordering_cases"], order_actions_llm, "LLM-based")
            )
        sections.append(
            "## 2. Action ordering\n\n"
            + fmt_ordering_table(ordering_rows)
            + f"\n\n{CRITICAL_LAST_NOTE}"
        )

    report = "\n\n".join(sections) + "\n"
    print(report)

    if args.out:
        Path(args.out).write_text(report)
        print(f"Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()