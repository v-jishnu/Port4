import asyncio
import json

from route_ticket import route_ticket, InvalidTicketError
from eval_dataset import EVAL_CASES


async def run_eval():
    results = []

    for case in EVAL_CASES:
        text = case["text"]

        if case.get("expect_rejection"):
            try:
                await route_ticket(text)
                results.append({"text": text, "passed": False, "note": "expected rejection, but ticket was routed"})
            except InvalidTicketError:
                results.append({"text": text, "passed": True, "note": "correctly rejected by guard"})
            continue

        try:
            ticket = await route_ticket(text)
        except InvalidTicketError as e:
            results.append({"text": text, "passed": False, "note": f"unexpectedly rejected: {e.reason}"})
            continue

        if case.get("expect_low_confidence"):
            passed = ticket.confidence < 60
            results.append({
                "text": text, "passed": passed,
                "actual_confidence": ticket.confidence,
                "note": "expected confidence < 60",
            })
            continue

        actual = {
            "category": ticket.category.value,
            "priority": ticket.priority.value,
            "team": ticket.team.value,
            "confidence": ticket.confidence,
        }
        expected = {
            "category": case["expected_category"],
            "priority": case["expected_priority"],
            "team": case["expected_team"],
        }
        passed = all(actual[k] == expected[k] for k in expected)
        # the failure mode that matters most: confidently wrong, since it would
        # never get flagged for human review by the confidence threshold alone
        high_confidence_miss = (not passed) and ticket.confidence >= 90

        results.append({
            "text": text,
            "passed": passed,
            "expected": expected,
            "actual": actual,
            "high_confidence_miss": high_confidence_miss,
            "note": case.get("note", ""),
        })

    return results


def summarize(results):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{passed}/{total} passed ({passed / total:.0%})")

    high_conf_misses = [r for r in results if r.get("high_confidence_miss")]
    if high_conf_misses:
        print(f"\n{len(high_conf_misses)} HIGH-CONFIDENCE MISS(ES) — confidently wrong, would not be caught by the review threshold:")
        for r in high_conf_misses:
            print(f"  \"{r['text'][:70]}\"\n    expected {r['expected']}\n    got      {r['actual']}")

    other_failures = [r for r in results if not r["passed"] and not r.get("high_confidence_miss")]
    if other_failures:
        print(f"\n{len(other_failures)} other failure(s):")
        for r in other_failures:
            detail = r.get("note") or f"expected {r.get('expected')}, got {r.get('actual')}"
            print(f"  \"{r['text'][:70]}\" -> {detail}")

    if passed == total:
        print("\nAll cases passed.")


if __name__ == "__main__":
    results = asyncio.run(run_eval())
    summarize(results)

    with open("eval_results_baseline.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved to eval_results_baseline.json — keep this as the 'before' snapshot for Phase 2's before/after comparison.")
