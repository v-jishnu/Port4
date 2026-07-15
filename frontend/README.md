# Frontend

A minimal, dependency-free web UI over the FastAPI backend — plain HTML/CSS/JS, no build step, no npm.

## Run it

```bash
uv run uvicorn main:app --reload
```

Then open **http://127.0.0.1:8000/** — that's it. `main.py` serves this folder directly (`app.mount("/", StaticFiles(directory="frontend", html=True))`), so starting the backend also starts the frontend; there's nothing separate to run or build.

## What's here

- **Submit** — type a ticket, see it classified live (category, priority, team, confidence, reasoning), or see the guard's rejection reason if it's invalid.
- **Team Queues** — pick a team, see what's routed to them, and act on any ticket: boost its confidence (optionally set a specific value), flag it to admin, or clear it from view (a soft delete — the record stays in the database, it just stops showing up in this list).
- **Admin** — every flagged ticket, with an inline correction form (category/priority/team/reasoning). Submitting a correction re-routes the ticket to its new team and disappears from this list. Both boosting and correcting a ticket automatically trigger a background semantic-memory sync — no separate step needed.
- **Metrics** — the last saved eval baseline (with a button to re-run all 20 cases live if you want a fresh number), a button to run the routing-time benchmark, and a quick breakdown of the unified ticket log by status.

## Design notes

- Talks to the backend via same-origin `fetch()` calls (`/route`, `/team-queue`, etc.) — no CORS configuration needed since it's served by the same FastAPI app.
- Kept intentionally independent of backend internals: it only ever calls the existing HTTP endpoints, the same ones the CLI's equivalent actions call into. Nothing here reaches into `ticket_log.py` or `route_ticket.py` directly.
- Re-running the eval from the UI never overwrites `eval_results_baseline.json` — only running `eval_harness.py` directly from the CLI does that, so the committed baseline snapshot stays stable regardless of how many times someone clicks the button in a demo.
