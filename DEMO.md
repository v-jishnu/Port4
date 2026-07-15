# Demo Walkthrough

This is the "run it and see it work" doc — a guided tour through the actual system, with real output captured from live runs, not fabricated examples. Read this first to see it working; read `README.md` for the architecture and design reasoning behind why it works this way.

## Setup

```bash
uv sync
cp .env.example .env   # then open .env and set OPENAI_API_KEY=sk-...
```

Everything below is run from the project root with `uv run`.

## 1. Submitting tickets

```bash
uv run cli.py submit
```

**A normal ticket:**
> `My order never arrived and it's been two weeks`

```
category=ORDER_ISSUE priority=MEDIUM team=FULFILMENT confidence=90
reasoning='The order has not arrived after the expected delivery time, indicating a shipment issue.'
```

**The same facts, said angrily — priority doesn't change:**
> `This is RIDICULOUS, my package STILL hasn't shipped after 10 days!!`

```
category=ORDER_ISSUE priority=MEDIUM team=FULFILMENT confidence=85
reasoning="The package has not shipped after the expected timeframe, indicating a fulfillment issue."
```

**Too vague to act on — rejected before it ever reaches the router:**
> `broken`

```
Error routing ticket: The ticket is too vague and does not specify any identifiable product, order, or issue.
```

**Empty input — rejected, not crashed:**
> `` (blank)

```
Error routing ticket: Ticket is either empty or too long.
```

**A boundary case — damaged in transit, still an order issue even though the customer wants a replacement:**
> `The blender I received arrived completely smashed, glass everywhere`

```
category=ORDER_ISSUE priority=HIGH team=FULFILMENT confidence=95
reasoning='The item arrived damaged with glass everywhere, indicating a shipping issue.'
```

**A multi-issue ticket — classified by the higher-priority issue, the other one named in reasoning:**
> `I still haven't gotten my refund from last month and now checkout keeps freezing`

```
category=BILLING_AND_PAYMENT priority=HIGH team=BILLING confidence=85
reasoning='The customer is experiencing a financial loss due to the missing refund and is also facing a technical issue with checkout freezing.'
```

## 2. The human-in-the-loop workflow

Using the ticket from the multi-issue example above:

```bash
uv run cli.py team-queue billing
```
```
Ticket ID: 6cc361b9-..., Category: billing_and_payment, Priority: high, Team: billing, Confidence: 85, ...
```

Billing decides the checkout-freeze part is really a fulfilment-side bug and flags it:
```bash
uv run cli.py flag 6cc361b9-...
```
```
Ticket 6cc361b9-... has been flagged to admin.
```

Admin reviews the flagged queue and re-routes it:
```bash
uv run cli.py admin-queue
uv run cli.py correct 6cc361b9-... --category order_issue --priority high --team fulfilment \
    --reasoning "Refund is separate; routing the checkout freeze as a fulfilment-side bug."
```
```
Ticket 6cc361b9-... corrected and re-routed to fulfilment.
```

A different, correctly-routed-but-low-confidence ticket gets confirmed instead of corrected:
```bash
uv run cli.py boost 5dd32705-... --confidence 96
```
```
Confidence for ticket 5dd32705-... has been boosted.
```

Both validated decisions are now eligible for semantic memory:
```bash
uv run cli.py sync-memory
```
```
Synced 2 human-validated ticket(s) into semantic memory.
```

## 3. FastAPI

```bash
uv run uvicorn main:app --reload
```
Open `http://127.0.0.1:8000/docs` for a browsable Swagger UI, or call it directly:

```bash
curl -X POST http://127.0.0.1:8000/route -H "Content-Type: application/json" \
     -d '{"text": "Does the Aria wool jacket run true to size?"}'
```
```json
{
  "input": "Does the Aria wool jacket run true to size?",
  "category": "product_inquiry",
  "priority": "low",
  "team": "sales",
  "confidence": 95,
  "reasoning": "This is a pre-purchase question about sizing with no existing order or issue."
}
```

## 4. The eval harness

```bash
uv run eval_harness.py
```
```
19/20 passed (95%)

1 other failure(s):
  "I still haven't gotten my refund from last month and now the checkout " -> multi-issue: refund (financial loss, higher priority) should win over the checkout bug

Saved to eval_results_baseline.json
```

Worth noting honestly: which single case fails occasionally varies between runs (this run it was the multi-issue priority call; other runs it's been a different borderline priority judgment) — category and team are consistently correct, it's specifically priority on genuinely debatable cases that occasionally flips even at `temperature=0`. See the README's *Reliability mechanisms* section for why, and `PHASE_2.md` for the full semantic memory design this eval baseline exists to measure against.

## Where to go next

- **`README.md`** — architecture, data model, design decisions, and the full deliverables/rubric mapping.
- **`CLI_GUIDE.md`** — every CLI command in detail.
- **`PHASE_2.md`** — semantic memory concepts, architecture, and code walkthrough.
- **`HANDOFF.md`** — a running context-sync log of what's built and what's left.
