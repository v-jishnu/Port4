# Phase 2 — Semantic Memory: Concepts, Architecture, and Code Walkthrough

This doc is written to teach, not just record — read it top to bottom once, and you should be able to explain, extend, and debug this phase yourself without re-reading the code cold.

## 1. What problem Phase 2 actually solves

Phase 1 gave you a router that classifies a ticket using only the examples written by hand into the system prompt. Those examples never change — no matter how many real tickets get corrected by a human, the router doesn't learn from any of it on its own.

Phase 2 closes that loop: every time a human validates a classification (either by `boost`-ing a low-confidence route that turned out correct, or by `correct`-ing a wrong one), that validated example becomes available for the router to consult on *future* tickets that resemble it. This is the standard shape of a **retrieval-augmented feedback loop**: humans correct the system, corrections get stored, stored corrections get retrieved and shown back to the model as extra context on similar future cases.

## 2. The concepts, from the ground up

### Embeddings

An embedding is a list of numbers (a vector) that represents the *meaning* of a piece of text. Two sentences with similar meaning get embeddings that are numerically close together; two unrelated sentences get embeddings that are numerically far apart. You don't design these numbers by hand — you send text to an embedding model (here, OpenAI's `text-embedding-3-small`) and it returns the vector.

```python
response = _openai_client.embeddings.create(model="text-embedding-3-small", input="my order never arrived")
vector = response.data[0].embedding   # a list of ~1536 floats
```

This is the exact same OpenAI account/API you're already using for classification — embeddings are just a different endpoint on the same client.

### Vector similarity search

Once every stored ticket has a vector, "find tickets similar to this new one" becomes a geometry problem: embed the new ticket, then find which stored vectors are numerically *closest* to it. "Closest" is measured by a distance metric — this project uses **cosine distance**, which ranges from 0 (identical meaning) to 2 (opposite meaning). A **vector database** (Chroma, here) exists specifically to store vectors and answer "give me the k closest ones to this query vector" efficiently, without you writing that search algorithm yourself.

Calibration data point from testing this build: two tickets about *different products* but the *same kind of complaint* ("my blender broke down right after first use" vs. a stored "espresso machine stopped working after just one use") measured **0.437** apart. Two tickets about the *same product* with very similar wording measured **0.207** apart. The threshold in this codebase (`SIMILARITY_DISTANCE_THRESHOLD = 0.4`) sits right between those — close enough to catch genuine near-duplicates, strict enough to reject "same vibe, different product." It's a tunable constant, not a proven-correct number — revisit it once real data accumulates.

### RAG (Retrieval-Augmented Generation)

The overall pattern this phase implements: **retrieve** relevant context from a store, then **generate** (classify) using that context alongside the original input. It's the same idea as the static few-shot examples already in your system prompt — this just makes the examples dynamic and specific to each incoming ticket, instead of fixed.

### Batch sync, not real-time

New human corrections don't get pushed into Chroma the instant they happen. Instead, a separate step (`sync-memory`) periodically pulls everything currently valid from `ticket_log.py` and pushes it into Chroma as a batch. This was a deliberate choice from the original plan, not an oversight — see §5.

## 3. Architecture: where this plugs into what you already built

```
                    ┌─────────────────────────────────────────────┐
                    │              ticket_log.py (SQLite)          │
                    │   the ONE source of truth for every ticket   │
                    └───────────────────┬───────────────────────────┘
                                         │
                         get_semantic_memory_candidates()
                          (source IN admin_corrected, confidence_boosted)
                                         │
                                         ▼
                              ┌────────────────────┐
                              │  sync_memory()      │   <- triggered manually,
                              │  (semantic_memory.py)│      via `cli.py sync-memory`
                              └──────────┬───────────┘
                                         │ embed + upsert by ticket id
                                         ▼
                              ┌────────────────────┐
                              │   Chroma (vector    │
                              │   store, on disk)   │
                              └──────────┬───────────┘
                                         │
                                queried by
                                         │
                              ┌──────────▼───────────┐
                              │ retrieve_similar(text) │
                              └──────────┬────────────┘
                                         │ returns 0-k similar validated tickets
                                         ▼
┌──────────────┐   guard    ┌────────────────────────┐   augmented   ┌──────────────┐
│  new ticket   │──────────▶│    route_ticket()       │──────────────▶│ router_agent  │
│    text       │  (as before)│  (route_ticket.py)     │  prompt text  │  (LLM call)   │
└──────────────┘            └────────────────────────┘               └──────────────┘
                                         │
                                         │ classified_ticket.input forced back
                                         │ to the ORIGINAL text (see §6)
                                         ▼
                              insert_ticket() -> ticket_log.py
                                (same as Phase 1, unchanged)
```

Nothing about the guard, the fallback path, or the logging path changed. The only new step is between "guard passes" and "call the router agent": retrieve, then augment.

## 4. The flow, step by step, for one real ticket

```
1. Customer/admin submits ticket text (CLI `submit`, or POST /route)
2. validate_ticket(text)  -- unchanged from Phase 1
3. retrieve_similar(text)
     - embed the ticket text
     - query Chroma for up to k=3 closest stored vectors
     - keep only matches with cosine distance <= 0.4
     - return [] if memory is empty or nothing is close enough
4. build_augmented_input(text, similar)
     - if similar is empty: return text unchanged (Phase 1 behavior, untouched)
     - else: append a "Similar past tickets validated by a human:" block,
       formatted exactly like the prompt's existing few-shot examples
5. Runner.run(router_agent, augmented_input)
     - the model sees the real ticket AND the reference block
     - the prompt explicitly tells it: use the reference only if it genuinely
       matches, and never copy any part of the reference block into "input"
6. classified_ticket.input = text   <- forced in code, not trusted to the model
7. insert_ticket(classified_ticket, source="llm")  -- unchanged from Phase 1
```

## 5. Design decisions, and the reasoning behind each

**OpenAI embeddings, not Chroma's built-in local model.** You're already authenticated to OpenAI for classification; reusing the same client keeps one provider, one API key, no extra model download. The tradeoff is a small per-embedding cost, which is negligible at this scale.

**Batch sync (`sync-memory` command) instead of syncing on every `boost`/`correct`.** Three reasons: (1) it keeps "when did memory last update" a visible, deliberate action rather than a hidden side effect of an unrelated command; (2) it naturally supports upserting many corrected tickets at once instead of one network round-trip per correction; (3) it matches the "before/after eval" methodology — you decide when memory changes, so you can measure its effect at a specific point in time rather than it drifting continuously mid-experiment.

**Upsert by ticket id, not insert.** `sync_memory()` always re-syncs the *entire* current set of valid tickets, keyed by their own database id. If a ticket gets boosted once, then later corrected again, re-running `sync-memory` replaces its old Chroma entry rather than leaving a stale duplicate sitting alongside the new one. Chroma's `.upsert()` does this for free — same call as `.add()` would be, but safe to call repeatedly on the same ids.

**A similarity threshold, not "always show the top-k regardless."** Early on, memory will be small and thematically scattered — the "closest" match to a query might still be a bad match. Filtering by `SIMILARITY_DISTANCE_THRESHOLD` means `retrieve_similar()` can honestly return nothing, and the router falls back to Phase 1 behavior for that ticket, rather than being fed a misleading "similar" example just because it was the least-dissimilar of a bad batch.

**No leakage — memory is only ever built from real corrections, never from `eval_dataset.py`.** This was true before this phase started and remains true: nothing in `sync_memory()` reads from the eval dataset, and you should never run an eval case through `correct`/`boost` to "seed" memory faster. If an eval ticket's exact text ended up embedded in memory, a later eval run would partly be measuring "did it memorize the answer," not "did retrieval genuinely help" — silently invalidating the whole before/after comparison this phase exists to enable.

**`classified_ticket.input` is force-overwritten in code, not trusted to the model.** The augmented prompt contains both the real ticket and a reference block. Even with an explicit prompt instruction not to echo the reference block into `input`, that's a request, not a guarantee — LLMs occasionally ignore formatting instructions under prompt pressure. Overwriting `classified_ticket.input = input_ticket` in Python, after the model responds, makes this a hard guarantee instead of a hope. This is the same "don't trust what you can enforce in code" instinct behind e.g. forcing `HumanRouted`'s confidence to 100 via a real Pydantic default rather than asking politely.

## 6. Code map — what's in each file and why

**`semantic_memory.py`** (new file, same pattern as `ticket_log.py` — one focused module, not folded into `route_ticket.py`):
- `_embed(text)` — the one place an OpenAI embedding call happens; everything else calls this rather than duplicating the API call.
- `sync_memory() -> int` — reads `get_semantic_memory_candidates()` from `ticket_log.py`, embeds each ticket's text, upserts into Chroma. Returns the count synced (0 if memory has nothing valid yet — not an error).
- `retrieve_similar(text, k=3) -> list[dict]` — embeds the query, asks Chroma for the k closest, filters by distance threshold, returns each match as `{"input", "category", "priority", "team", "reasoning", "distance"}`. Returns `[]` on an empty collection or no close-enough matches.

**`route_ticket.py`** — three changes:
1. New import: `from semantic_memory import retrieve_similar`.
2. New function `build_augmented_input(ticket_text, similar)` — pure text formatting, no side effects, easy to test in isolation.
3. Inside `route_ticket()`: `retrieve_similar()` is called in its **own try/except**, separate from the router call — if Chroma or the embedding API has a problem, retrieval silently degrades to `[]` (Phase 1 behavior) rather than blocking classification entirely. Same "narrow try blocks, one per failure domain" principle from Phase 1's logging fix.

**`cli.py`** — one new subcommand, `sync-memory`, calling `sync_memory()` and printing the count. No arguments needed.

**System prompt (`route_ticket.py`)** — one new section, `# SIMILAR PAST TICKETS`, telling the model: treat the reference block as a hint not a rule, ignore it if the current ticket differs in anything that matters, and never copy it into the `input` field.

**`.gitignore`** — added `chroma_memory/` (Chroma's on-disk index files), same reasoning as `tickets.db`: generated runtime data, not source.

**`pyproject.toml`** — added `chromadb` via `uv add chromadb`.

## 7. What was actually verified, live

- Empty memory: `sync_memory()` returns `0`, `retrieve_similar()` returns `[]`, and a ticket routes identically to Phase 1 (confirmed no augmentation happens with nothing to retrieve).
- Seeded one real human-validated correction (an espresso machine ticket, wording deliberately different from anything in `eval_dataset.py`), ran `sync-memory`, confirmed it reported syncing 1 ticket.
- Queried a genuinely similar new ticket (different product, same complaint type) — correctly returned nothing, distance (0.437) fell just outside the threshold.
- Queried a near-duplicate ticket (same product, similar wording) — correctly retrieved the seeded example (distance 0.207).
- Ran a near-duplicate ticket through the **full** `route_ticket()` pipeline — classified correctly, and confirmed via direct DB inspection that `input` was stored as the clean original text on both the seed ticket and the new one, with no contamination from the injected reference block.
- Full regression pass: guard rejection (empty + gibberish) still works, FastAPI `/route` still works, `temperature=0` still holds on both agents, CLI lifecycle unaffected.

## 8. The eval number — read this before trusting any percentage

`eval_results_baseline.json` currently shows **100% (16/16)**, generated with an **empty** memory (no real corrections synced) but with the *new* system prompt (the added `# SIMILAR PAST TICKETS` section) already in place. The **true pre-Phase-2 number, from earlier in this build, was 94% (15/16)** — that run predates any Phase 2 code and is only recorded in conversation history, not in a separate file, because re-running `eval_harness.py` during development overwrote the original file.

What this means practically: don't read 94% → 100% as "memory improved accuracy" — memory was empty both times. The honest comparison to make **going forward** is: populate memory with real corrected tickets over time, run `sync-memory`, re-run `eval_harness.py`, and diff against the current 100%/16-16 file. That's the real before/after this phase was built to enable — it just hasn't happened yet, because a fresh system has no real correction history to learn from.

## 9. What's tunable, and what to watch as real data accumulates

- `SIMILARITY_DISTANCE_THRESHOLD` (0.4) and `k` (3, in `retrieve_similar`'s default) — both guesses calibrated on two data points. Revisit once you have dozens of real corrected tickets to test against.
- If retrieval starts pulling in a *wrong* example that measurably drags classifications off course, the fix is almost certainly the threshold, not the prompt wording — check `distance` values on the bad case first.
- Nothing currently limits how large Chroma's collection grows, or expires old corrections — not a problem at this scale, worth knowing about before this runs in production for months.
