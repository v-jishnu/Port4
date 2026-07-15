# Handoff — Smart Ticket Router (as of the logging + CLI phase)

## Mission
Internship project, mentor-graded on a rubric (~48% weight on Mission-Specific + Integration Quality — mainly JSON reliability and edge-case handling). Two-week build, started 2026-07-11.

Goal: `route_ticket(text) -> RoutedTicket`, a reusable function returning structured JSON (`category`, `priority`, `team`, `confidence`, `reasoning`), reused across a CLI, a FastAPI endpoint, and an eval harness ("one brain, many mouths").

## Stack
Python (>=3.12), `openai-agents` SDK (`Agent` / `Runner`, not raw `openai` client), Pydantic v2, `sqlite3` (stdlib) for persistence, FastAPI + uvicorn (not wired up yet), python-dotenv, `uv` for package management. Model `gpt-4o-mini`, **`temperature=0` on both agents** via `ModelSettings(temperature=0)` — confirmed live on both `router_agent` and `guardrail_agent`, non-negotiable per the rubric's same-input consistency requirement.

## What's built

**`schemas.py`** — `Category` / `Priority` / `Teams` enums, `TicketOutput` (input, category, priority, team, confidence 0-100, reasoning), `HumanRouted(TicketOutput)` (confidence defaults to 100, not hard-locked — this turned out to matter later, see `ticket_log.py`). `needs_clarification` and `secondary_category` deliberately dropped — confidence covers vagueness, `reasoning` prose covers ambiguity (including multi-issue tickets, see below).

**`input_guard.py`** — `guardrail_agent` decides if text is a real, in-scope e-commerce ticket. `async def validate_ticket(text) -> ValidTicket` does a manual length/empty check first, otherwise calls the guard agent — always returns a `ValidTicket` on every path, never `None`. `temperature=0` set. CLI driver under `__main__`, safe to import from.

**`route_ticket.py`** — `router_agent` classifies into category/priority/team/confidence/reasoning. System prompt includes category boundary rules, a business-impact priority rubric, deterministic category→team mapping, confidence calibration bands (90-100 / 60-89 / <60), and a **multi-issue ticket rule**: when a ticket describes 2+ distinct issues, classify by whichever carries higher priority, name the secondary issue explicitly in `reasoning`, cap confidence in the 60-89 band. `async def route_ticket(text) -> TicketOutput` is the core function: calls the guard, raises `InvalidTicketError(reason)` if rejected; otherwise calls the router agent, with a safe fallback (`product_inquiry/low/confidence=0`) if the LLM call itself fails. Every outcome (LLM success, LLM-failure fallback) gets logged via `insert_ticket`, each logging call independently try/except-wrapped so a persistence failure can never mask or override a correct classification — this was a real bug, caught live (a DB hiccup was silently swallowing correct classifications and replacing them with the fallback before the fix).

**`ticket_log.py`** — SQLite-backed persistence (`tickets.db`, gitignored), chosen over a flat log file specifically because the workflow needs *mutation* (a team updating one ticket's confidence or status), not just appending. One `tickets` table, all "logs" are just filtered queries over it:
- `insert_ticket(ticket, source)` — status derived from confidence (`routed` if ≥60, `below_threshold` if <60 — sub-60 tickets are deliberately never shown to any team, a conscious tradeoff, not a bug); `source` always `"llm"` or `"fallback"` at insert time.
- `flag_to_admin(id)` — team marks a ticket wrong/not theirs → `status='flagged_to_admin'`.
- `boost_confidence(id, new_confidence=90)` — team confirms a low-confidence route was actually correct → `source='confidence_boosted'`, `status` untouched (still `routed`).
- `admin_correct(id, input_text, category, priority, team, reasoning)` — re-validates via `HumanRouted` (catches bad admin input the same way a bad LLM output would be caught), sets `status='routed'` (so the corrected ticket flows into whichever team it was re-routed to) and `source='admin_corrected'` (permanent tag, independent of `status`).
- **Why `status` and `source` are separate columns**: originally one field did both jobs, and it broke — an admin-corrected ticket became invisible to every team queue because `status='admin_corrected'` didn't match any queue's `WHERE status='routed'` filter. Splitting into workflow-state (`status`) vs. provenance (`source`) fixed it and is the exact mechanism Phase 2 will use to find human-validated rows.
- View functions: `get_unified_log()`, `get_team_queue(team)`, `get_admin_queue()`, `get_ticket_by_id(id)`, `get_semantic_memory_candidates()` (filters `source IN ('admin_corrected', 'confidence_boosted')` — the only rows Phase 2 should learn from).

**`cli.py`** — argparse-based, 6 subcommands: `submit`, `team-queue <team>`, `admin-queue`, `flag <id>`, `boost <id> [--confidence]`, `correct <id> --category --priority --team --reasoning`. This is the interface that actually exercises the human-in-the-loop workflow — before this, `flag_to_admin`/`boost_confidence`/`admin_correct` existed but nothing ever called them. Full lifecycle (submit → team sees it → boost or flag → admin corrects → re-routed to new team) verified live end-to-end.

## Verified working end-to-end (live runs, not just code review)
- Guard rejection: empty/oversized ticket (manual check) and gibberish (LLM guard) — both correctly short-circuit before the router runs.
- Valid tickets route correctly with `temperature=0` confirmed on both agents.
- Full CLI lifecycle: `submit` → `boost` (confidence updated, status untouched) → `flag` → `correct` (re-routed to a *different* team, admin queue clears, new team's queue shows it, confidence forced to 100) → `get_semantic_memory_candidates()` returns exactly the boosted + corrected rows, nothing else.
- Simulated failures: LLM outage alone → graceful fallback; LLM outage *and* DB failure simultaneously → still returns the fallback ticket instead of crashing (logging and classification failures are independent).

## Known issues / not yet fixed (low priority, left as-is deliberately)
- `pyproject.toml` still lists `asyncio>=4.0.0` as a dependency — unnecessary, `asyncio` is stdlib.
- `router_agent`'s system prompt has a few words truncated mid-token from an early paste (e.g. "refunndow", "isproduct_inquiry") — doesn't block correctness in practice but worth a proofread pass eventually.
- `insert_ticket`'s `source` parameter is a freeform string, not enum-validated — low risk today (only 2 call sites, both correct), but a future typo would silently create an unfindable row.
- `cli.py` imports `TicketOutput` from `schemas` but never uses it directly.

## Not started yet
FastAPI endpoint (`main.py` is still an unused placeholder hello-world) — next up. Then eval harness (must come *before* Phase 2 semantic memory, so there's a baseline to measure "before/after" against — this ordering was a deliberate correction to the original plan). Then Phase 2 (Chroma-based retrieval over `get_semantic_memory_candidates()`, batch sync, no leakage). Memsy (an org-tiered multi-user memory platform) was evaluated and rejected as a fit — solves a different, bigger problem than this project's narrow single-corpus retrieval need; Chroma remains the plan.
