# Handoff — Smart Ticket Router (as of commit 969c684)

## Mission
Internship project, mentor-graded on a rubric (~48% weight on Mission-Specific + Integration Quality — mainly JSON reliability and edge-case handling). Two-week build, started 2026-07-11.

Goal: `route_ticket(text) -> RoutedTicket`, a reusable function returning structured JSON (`category`, `priority`, `team`, `confidence`, `reasoning`), reused across a CLI, a FastAPI endpoint, and an eval harness ("one brain, many mouths").

## Stack
Python (>=3.12), `openai-agents` SDK (`Agent` / `Runner`, not raw `openai` client), Pydantic v2, FastAPI + uvicorn (not wired up yet), python-dotenv, `uv` for package management. Model `gpt-4o-mini`, temperature 0 (non-negotiable — rubric checks same-input consistency).

## What's built

**`schemas.py`** — `Category` (order_issue / billing_and_payment / product_inquiry / technical_support), `Priority` (low/medium/high), `Teams` (fulfilment/billing/sales/technical_support) enums, `TicketOutput` (input, category, priority, team, confidence 0-100, reasoning) and `HumanRouted(TicketOutput)` (confidence pinned to 100). `needs_clarification` and `secondary_category` were deliberately dropped — confidence covers vagueness, `reasoning` prose covers ambiguity.

**`input_guard.py`** — `guardrail_agent` (gpt-4o-mini) decides if text is a real, in-scope e-commerce support ticket. `async def validate_ticket(text) -> ValidTicket` does a manual length/empty check first (no wasted LLM call on obviously-bad input), otherwise calls the guard agent. Always returns a `ValidTicket` on every path (never `None`) — that consistency was a real bug fixed this session. CLI driver is under `if __name__ == "__main__":`, safe to import from.

**`route_ticket.py`** — `router_agent` (gpt-4o-mini) classifies a validated ticket into category/priority/team/confidence/reasoning per a system prompt with explicit category boundary rules, a business-impact priority rubric, a deterministic category→team mapping, confidence calibration guidance, and few-shot examples. `async def route_ticket(text) -> TicketOutput` is the core orchestrating function: calls `validate_ticket` first, raises `InvalidTicketError(reason)` if rejected, otherwise calls `router_agent` and returns the classified result. CLI driver under `__main__`, single guard call, try/except around the one entry point.

**Architecture decided along the way:** guard and router are two separate LLM calls (not merged into one prompt) — keeps single-responsibility prompts, avoids polluting the schema/confidence semantics with a "not a ticket at all" case, and lets junk get filtered before touching logs. The core `route_ticket()` function takes a plain string and either returns or raises — no interface (CLI/FastAPI/eval) does its own guard logic, they all just call this one function.

## Verified this session (live runs, not just code review)
- Valid ticket → correctly routed with sensible category/priority/team/confidence/reasoning.
- Empty/oversized ticket → rejected by the manual guard.
- Gibberish ("jgfsjehdgfwkeay") → rejected by the LLM guard, no wasted router call.

## Known issues / immediate TODOs (not yet fixed as of this commit)
- `input_guard.py`'s `validate_ticket` still has a leftover `print(...)` on the manual-length-reject path — causes a **double-printed message** when combined with `route_ticket.py`'s own exception-reason print. Should be removed (core functions shouldn't print).
- `route_ticket.py` has an unused `from pydantic import BaseModel` import.
- `pyproject.toml` lists `asyncio>=4.0.0` as a dependency — unnecessary, `asyncio` is stdlib.
- `router_agent`'s system prompt string has several words truncated mid-token (e.g. "refunndow", "isproduct_inquiry") from an earlier paste — needs a proofread pass since it affects real classification accuracy.

## Not started yet
FastAPI endpoint (`main.py` is still an unused placeholder hello-world), CLI polish beyond the raw `input()` driver, eval harness, and Phase 2 (Chroma-based retrieval of human corrections, batch sync, before/after eval).
