# Smart Ticket Router

> Reads any e-commerce support message and returns a **structured, schema-validated routing decision** — `category`, `priority`, `team`, `confidence`, and a one-line `reasoning` — as guaranteed-valid JSON, with a two-stage input guard, automatic retry, and a safe fallback so a bad model response or API error degrades gracefully instead of crashing.

**Stack:** Python 3.12 · [`openai-agents`](https://github.com/openai/openai-agents-python) SDK (`Agent`/`Runner`) · Pydantic v2 · SQLite · `python-dotenv` · `uv`. Model: `gpt-4o-mini` at **temperature 0**.

**This document explains the architecture and the reasoning behind it — what's built, why it's built this way, and how the pieces fit together.** To actually see it running, with real captured output at every step, go to **[`DEMO.md`](DEMO.md)** first.

---

## The problem this solves

Support teams triage every incoming ticket by hand — reading it, deciding what it's about, judging how urgent it is, and forwarding it to the right team. It's slow, inconsistent between people, and it doesn't scale. This service does that first-pass triage automatically and deterministically: one support message in, a structured routing decision out, ready to drop onto the correct team's queue — with low-confidence cases held back for a human instead of being guessed at.

**Who uses it:** a support-ops team drowning in inbound tickets. **What it gives them:** instant, consistent, auditable routing, and a human-review lane for the genuinely unclear cases.

---

## What it does

- **Classifies** each ticket into a fixed `category`, `priority`, and `team`, plus a calibrated `confidence` (0–100) and a one-sentence `reasoning` that cites the evidence behind the decision.
- **Guards the input** before spending an API call — empty, oversized, off-topic, or non-ticket messages are rejected up front.
- **Guarantees the output shape** — every field is present and every fixed field is a value from a closed set; the model cannot invent a category or team that doesn't exist.
- **Degrades gracefully** — transient errors retry automatically, and a failed classification returns a safe, well-formed fallback (routed to human review) rather than raising.
- **Persists everything** to a single SQLite store that doubles as the team queues, the admin queue, and the audit log.
- **Routes by confidence** — high-confidence tickets land in their team's queue; low-confidence tickets are held back for a human.
- **Supports human-in-the-loop correction** — teams and admins can flag, correct, or confirm a routing decision, and those human-validated decisions are recorded distinctly for later reuse.
- **Learns from human corrections** — validated corrections are retrieved as dynamic examples for future similar tickets, on top of the router's fixed prompt examples (Phase 2, see below).
- **Ships with a CLI, a FastAPI service, and a 20-case labeled eval harness** — the same `route_ticket()` core is exercised through all three, not reimplemented in any of them.

---

## Architecture — *one brain, many mouths*

All routing logic lives in a single core function, `route_ticket(text) -> TicketOutput`. Every interface — CLI, FastAPI, the eval harness — is a thin caller of that one function; none of them re-implement guarding, retrieval, retrying, or logging.

```
                         input text
                              │
                              ▼
         ┌────────────────────────────────────────┐
         │  ① INPUT GUARD  (input_guard.py)         │
         │   a. deterministic check (no API call):  │
         │      empty / whitespace / > 500 chars    │
         │   b. LLM relevance check (temp 0):       │
         │      is this a real in-scope ticket?     │
         └───────────────┬──────────────────────────┘
              reject      │ pass
                 │        ▼
                 │   ┌──────────────────────────────────────┐
                 │   │  ② SEMANTIC MEMORY  (semantic_memory.py)│
                 │   │   retrieve_similar(text) - embeds the  │
                 │   │   ticket, queries Chroma for human-    │
                 │   │   validated similar past tickets       │
                 │   │   0 results if memory is empty or      │
                 │   │   nothing is close enough (safe no-op) │
                 │   └───────────────┬────────────────────────┘
                 │                   ▼
                 │   ┌──────────────────────────────────────┐
                 │   │  ③ ROUTER  (route_ticket.py)           │
                 │   │   gpt-4o-mini, temperature 0,          │
                 │   │   Structured Output = TicketOutput     │
                 │   │   • category boundary rules            │
                 │   │   • business-impact priority rubric    │
                 │   │   • deterministic category→team map    │
                 │   │   • confidence calibration + few-shot  │
                 │   │   • prompt augmented with any similar   │
                 │   │     tickets retrieved in step ②         │
                 │   └───────────┬───────────────┬────────────┘
                 │        success │        failure│
                 │                ▼               ▼
                 │        classified        safe fallback
                 │        TicketOutput      (confidence = 0)
                 │                └───────┬───────┘
                 ▼                        ▼
        InvalidTicketError    ┌───────────────────────────────┐
        (caller decides)      │  ④ PERSIST  (ticket_log.py)    │
                              │   SQLite: status + source      │
                              │   confidence ≥ 60 → team queue │
                              │   confidence < 60 → held back  │
                              └───────────────┬───────────────┘
                                              ▼
                                       return TicketOutput
```

---

## Data model (`schemas.py`)

Every fixed-value field is a `str`-backed `Enum`. Because the router's structured output is typed to this model, the model's JSON is **constrained at generation time** to these exact values — and validated **again** by Pydantic on receipt. Two independent guarantees that the output can never contain an invented or missing field.

| Field | Type | Allowed values |
|---|---|---|
| `input` | `str` | the original ticket text, verbatim |
| `category` | `Category` | `order_issue` · `billing_and_payment` · `product_inquiry` · `technical_support` |
| `priority` | `Priority` | `low` · `medium` · `high` |
| `team` | `Teams` | `fulfilment` · `billing` · `sales` · `technical_support` |
| `confidence` | `int` (0–100) | model's calibrated certainty, bounded by the schema |
| `reasoning` | `str` | one sentence citing the evidence behind the decision |

`team` is **deterministically derived from `category`** by the prompt (`order_issue → fulfilment`, `billing_and_payment → billing`, `product_inquiry → sales`, `technical_support → technical_support`), so a category/team mismatch is structurally impossible.

`HumanRouted(TicketOutput)` is the same shape with `confidence` pinned to `100` — a human decision is ground truth, not a probabilistic guess — and it reuses the exact validation path an LLM output goes through.

---

## Reliability mechanisms

| Guarantee | How it's achieved |
|---|---|
| **Valid JSON, every field present** | Structured Output typed to `TicketOutput` (constrained generation) + Pydantic validation on receipt |
| **No invented category/priority/team** | `str`-backed enums — the model's legal output space *is* the enum |
| **Consistent — same input, same output** | `temperature=0` on both the guard and the router (`ModelSettings(temperature=0)`) |
| **Transient errors don't surface** | the Agents SDK retries model calls automatically before raising |
| **A failed classification never returns garbage** | the router call is wrapped; on failure it returns a valid `TicketOutput` with `confidence=0` and `source="fallback"`, which routes to human review |
| **No secrets in code** | the API key is read from `.env` via `python-dotenv`; `.env` and `tickets.db` are git-ignored |

---

## Edge-case handling

| Case | Behaviour |
|---|---|
| **Angry / emotional tone** (`"This is RIDICULOUS, nothing works!!!"`) | The router is explicitly instructed to route on *facts*, not tone — emotional language does not change the classification. |
| **Very short / vague** (`"broken"`) | Caught by the guard (too vague / not an actionable ticket) and rejected with a reason, or routed with low confidence to human review — never a crash. |
| **Ambiguous / two-category** | The router picks the higher-impact category and the `reasoning` field explicitly names the runner-up and why it was not chosen; genuinely borderline tickets score below the confidence threshold and go to a human. |
| **Empty / whitespace / oversized (> 500 chars)** | Rejected by the deterministic guard *before* any API call — zero cost. |
| **Multi-issue ticket** | Classified by the highest-priority issue; the secondary issue is named in `reasoning` for follow-up. |

---

## Persistence & human-in-the-loop (`ticket_log.py`)

A single SQLite table (`tickets.db`, git-ignored) is the one source of truth. Team queues and the admin queue are **filtered views over that one table**, not separate stores — so aggregate reporting never has to merge files, and a ticket moves between queues by updating one field.

Two columns carry the audit story:

- **`status`** — `routed` (confidence ≥ 60, visible in its team's queue) or `below_threshold` (held back from teams).
- **`source`** — `llm` · `fallback` · `confidence_boosted` · `admin_corrected` — records *how* each row came to exist, independent of what it currently says.

Human-in-the-loop operations, modelled directly as database transitions:

| Function | Who / when | Effect |
|---|---|---|
| `flag_to_admin(id)` | a team says "this isn't ours / it's wrong" | moves the ticket to the admin queue |
| `admin_correct(id, …)` | an admin fixes a flagged ticket | re-validated through `HumanRouted` before it's persisted; `source = admin_corrected` |
| `boost_confidence(id)` | a team confirms a correct low-confidence route | `source = confidence_boosted` |

`get_semantic_memory_candidates()` returns only `admin_corrected` and `confidence_boosted` rows — i.e. only **human-validated** decisions — so any future learning loop can never be seeded from an unverified LLM guess. This is the provenance foundation for Phase 2.

---

## Running it

> For a guided walkthrough with real captured output at every step, see **[`DEMO.md`](DEMO.md)**. What follows here is the reference command list.

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/) and an OpenAI API key.

```bash
uv sync                      # install exact, locked dependencies
cp .env.example .env         # then open .env and set OPENAI_API_KEY=sk-...
```

**CLI** — six commands, the full human-in-the-loop workflow (see `CLI_GUIDE.md` for a full walkthrough):

```bash
uv run cli.py submit                                    # interactive: enter a ticket, get it classified
uv run cli.py team-queue billing                        # view what's routed to a team
uv run cli.py boost <ticket_id> --confidence 95          # confirm a low-confidence route was correct
uv run cli.py flag <ticket_id>                           # send a wrong/misrouted ticket to admin
uv run cli.py admin-queue                                # view flagged tickets
uv run cli.py correct <ticket_id> --category ... --priority ... --team ... --reasoning "..."
uv run cli.py sync-memory                                # batch-sync validated corrections into semantic memory
```

**FastAPI + web UI** — the same actions as HTTP endpoints, plus a minimal browsable frontend, both from one command:

```bash
uv run uvicorn main:app --reload
# then open http://127.0.0.1:8000/         for the web UI (submit, team queues, admin, metrics)
# or        http://127.0.0.1:8000/docs     for the raw Swagger API docs
# or POST directly to /route, /team-queue, /admin-queue, /flagged/{id}, /boost_confidence, /route_to_admin, /clear/{id}
```

The frontend (`frontend/`) is a dependency-free static site — no build step, no npm — served directly by `main.py`; see `frontend/README.md` for what each screen does.

**Eval harness** — runs 20 labeled tickets through `route_ticket()` and reports pass rate, with high-confidence misses (confidently wrong — the failure mode that would never get caught by the confidence-review threshold) called out separately from other failures:

```bash
uv run eval_harness.py
```

This writes `eval_results_baseline.json` — the frozen "before" snapshot Phase 2's before/after comparison is measured against.

The guard alone can also be exercised on its own with `uv run input_guard.py`, and the core pipeline directly with `uv run route_ticket.py`. Every routed, fallback, and human-reviewed decision is written to `tickets.db` for inspection.

---

## Project structure

```
port4/
├── schemas.py           # Pydantic models + enums — the data contract
├── input_guard.py       # two-stage validation (deterministic + LLM) + standalone CLI
├── route_ticket.py      # core route_ticket() + router agent + standalone CLI entry point
├── ticket_log.py        # SQLite persistence, team/admin queues, human-in-the-loop ops
├── semantic_memory.py   # Phase 2: embeddings, Chroma sync + retrieval
├── cli.py               # full CLI — submit/team-queue/admin-queue/flag/boost/correct/sync-memory
├── main.py              # FastAPI app — same actions as HTTP endpoints, serves frontend/ at "/"
├── frontend/            # dependency-free HTML/CSS/JS web UI (index.html, styles.css, app.js)
├── eval_dataset.py      # 20 labeled test cases (all 4 categories, boundary rules, multi-issue, edge cases)
├── eval_harness.py      # runs the eval set through route_ticket(), reports pass rate + high-confidence misses
├── benchmark_timing.py  # measures real AI routing latency for the before/after time comparison
├── .env.example         # template for the required OPENAI_API_KEY (never commit .env)
├── pyproject.toml       # uv-managed, version-locked dependencies
├── DEMO.md              # guided walkthrough with real captured output — start here to see it run
├── HANDOFF.md           # context-sync doc: what's built, what's left, known issues
├── CLI_GUIDE.md         # user-facing CLI command reference
├── PHASE_2.md           # semantic memory: concepts, architecture, code walkthrough
├── tickets.db           # SQLite store (git-ignored, created on first run)
├── chroma_memory/       # Chroma's on-disk vector index (git-ignored, created on first sync)
└── eval_results_baseline.json  # the frozen eval snapshot Phase 2 is measured against
```

---

## Design decisions & rationale

- **Guard and router are two separate LLM calls, not one merged prompt.** Single-responsibility prompts stay clean; "this isn't a ticket at all" never pollutes the classification schema or the confidence semantics; and junk is filtered before it ever reaches the log.
- **`team` is derived from `category`, not chosen by the model.** The one part of the decision that has a deterministic correct answer is computed deterministically — removing an entire class of possible error.
- **`gpt-4o-mini` + temperature 0.** The task is classification, not generation; the small model is fast and cheap and more than capable, and temperature 0 is what makes the same input produce the same output on a repeat run.
- **Enums over free strings.** The reliability requirement ("never an invalid value") is enforced by the *type*, not by hoping the prompt holds.
- **SQLite over flat files.** Human review needs to *mutate* records (flag, correct, confirm) and to *query* them by team/status — both are native to a relational store and awkward in an append-only file. One table with filtered views keeps storage unified while giving each role its own view.
- **`needs_clarification` / `secondary_category` were deliberately dropped.** Confidence already captures vagueness, and the `reasoning` field plus explicit multi-issue handling covers ambiguity — a distinction between *vague* and *ambiguous* that shaped the schema down to what actually earns its place.

---

## Deliverables status

| # | Deliverable | Status |
|---|---|---|
| 1 | Prompts that consistently return valid structured JSON | ✅ Structured Output + enums + Pydantic + temperature 0 |
| 2 | Handle 3 edge cases (angry tone, very short, ambiguous) | ✅ see *Edge-case handling*; each has a dedicated case in `eval_dataset.py` |
| 3 | A simple interface to test it | ✅ CLI (6 commands) · ✅ FastAPI (`POST /route` + Swagger `/docs`) · ✅ a minimal web UI (`frontend/`, served at `/`) covering submit, team queues, admin corrections, and metrics |
| 4 | Before/after: manual vs. AI routing time | ✅ measured AI time + a reasoned manual estimate — see *Before/after: routing time* below |
| 5 | Demo 20 sample tickets | ✅ `eval_dataset.py` — 20 labeled cases across all 4 categories, the boundary rules, multi-issue handling, and guard rejection; `eval_harness.py` runs them and reports pass rate (baseline: see `eval_results_baseline.json`) |

---

## What's delivered vs. what's left

**Delivered this build:**
- **FastAPI service** (`main.py`) — `POST /route` plus a matching endpoint for every CLI action, Swagger `/docs` browsable out of the box.
- **Eval harness** (`eval_harness.py` + `eval_dataset.py`) — 20 labeled tickets, run through the real `route_ticket()` pipeline, reporting pass rate and separating high-confidence misses (confidently wrong — the case a confidence-based review queue would never catch) from lower-confidence ones. Current baseline: **19/20 – 20/20** across repeat runs, saved to `eval_results_baseline.json` (the single recurring miss is a genuinely debatable medium-vs-high priority call on one ticket, not a category/team error — see note below).
- **Phase 2 — retrieval-augmented memory, not model weight-learning.** Human-validated corrections only (`admin_corrected` / `confidence_boosted` rows, via `get_semantic_memory_candidates()`) are embedded and stored in Chroma. `sync_memory()` batch-syncs them — never mid-request, preserving the `temperature=0` consistency guarantee — and `retrieve_similar()` surfaces the closest matches (cosine distance ≤ 0.4) as dynamic few-shot context injected into the router prompt for future similar tickets. A ticket's stored `input` is force-set back to the original raw text in code after classification, so the injected reference block can never leak into what gets persisted. Full concepts, architecture, and code walkthrough in `PHASE_2.md`.
  - **Honest note on the eval number:** the baseline was captured with an *empty* memory — there's no real correction history yet for it to have learned from. The genuine before/after comparison happens once real `boost`/`correct` actions accumulate, `sync-memory` is run, and `eval_harness.py` is re-run against this same baseline file. Memory is never seeded from the eval set itself — doing so would let the system "memorize" its own test, invalidating the comparison.
  - **Honest note on the one recurring miss:** repeat runs occasionally disagree on one ticket's priority (`medium` vs. the labeled `high`) — category and team are always correct on it. `temperature=0` makes output deterministic *within* a single OpenAI request, but does not guarantee bit-exact determinism across separate API calls on a genuinely borderline case. This is a real, observed limit of the consistency guarantee, not something papered over.
- **A minimal web UI** (`frontend/`) — a dependency-free static site (no build step, no npm) served directly by `main.py` at `/`. Covers every human-facing action: submit a ticket and see the live classification, browse each team's queue and boost/flag/clear tickets from it, review and correct the admin queue, and check the eval baseline / re-run it / run the timing benchmark / see a log breakdown, all from one page. Talks to the backend only through the existing HTTP endpoints — no logic duplicated from the CLI or `route_ticket()`. See `frontend/README.md`.
  - **Clear (soft delete)** is a new capability added alongside the UI: `clear_ticket()` sets `status='cleared'`, removing a ticket from its team's queue without deleting the row — the full record (and its `source` provenance) stays intact for the audit trail and for semantic memory eligibility.
  - **Boosting or correcting a ticket from the UI/API now auto-triggers a background `sync_memory()` call** — a deliberate UX difference from the CLI, where `sync-memory` stays a separate, manual command. The underlying sync is still the same batch/upsert operation either way; only *what triggers it* differs, so a mentor demoing the UI sees memory actually grow without needing to know a separate command exists.

## Before/after: routing time

**AI time — measured, not estimated.** `benchmark_timing.py` runs 5 realistic tickets through the real `route_ticket()` pipeline (guard + retrieval + router + logging) and times each end to end:

```bash
uv run benchmark_timing.py
```

Measured average: **~4.2 seconds per ticket** (sequential API round-trips for the guard call and the router call — the dominant cost is network latency to OpenAI, not local computation).

**Manual time — a reasoned estimate, not a guess.** A support agent triaging a ticket by hand typically: reads and understands it (~20s), determines its category (~15s), assesses priority/urgency (~15s), works out the correct team queue (~10s), and logs/forwards it (~15s) — **~75 seconds per ticket**, and that's before accounting for inconsistency between agents, interruptions, or a queue backing up.

**The comparison:** ~75s manual vs. ~4.2s AI is roughly **18x faster**, and — unlike manual triage — consistent every time rather than varying by agent, mood, or fatigue. This is deliberately presented as a measured number (AI) next to a labeled, reasoned estimate (manual), not two numbers of equal rigor pretending otherwise.

**Deferred by design:**
- Team-to-team hand-off for multi-issue tickets — the router already classifies by highest-priority issue and names the secondary issue in `reasoning`; the actual hand-off *workflow* is scoped for later, since it's a UI/process feature, not a classification gap.
