# Ticket Router CLI — User Guide

A command-line tool for submitting support tickets, reviewing team queues, and handling admin corrections. Every command is run with `uv run cli.py <command> ...`.

## Setup

Make sure you have a `.env` file in the project root with your `OPENAI_API_KEY` set (see `.env.example`). No database setup needed — `tickets.db` is created automatically the first time you run anything.

## Commands at a glance

| Command | What it does | Who uses it |
|---|---|---|
| `submit` | Submit a new ticket for classification | Anyone raising a ticket |
| `team-queue <team>` | View tickets currently routed to a team | Team members |
| `boost <id>` | Confirm a low-confidence route was actually correct | Team members |
| `flag <id>` | Flag a ticket as wrong or not your team's | Team members |
| `admin-queue` | View tickets flagged for admin review | Admin |
| `correct <id>` | Fix a flagged ticket's classification and re-route it | Admin |

---

## `submit` — raise a new ticket

```
uv run cli.py submit
```
You'll be prompted to type the ticket text. The system validates it, classifies it, and prints the result:
```
Enter your query to be raised as a ticket: My order never arrived after two weeks
Ticket routed successfully: input='My order never arrived after two weeks' category=<Category.ORDER_ISSUE: 'order_issue'> priority=<Priority.HIGH: 'high'> team=<Teams.FULFILMENT: 'fulfilment'> confidence=95 reasoning='...'
```
If the ticket is empty, too long, or too vague to be a real support ticket, it's rejected before classification ever runs:
```
Invalid ticket: The ticket is too vague and does not provide any relevant information.
```

---

## `team-queue` — view what's routed to your team

```
uv run cli.py team-queue billing
```
Valid team names: `fulfilment`, `billing`, `sales`, `technical_support`.

Prints every ticket currently routed to that team:
```
Ticket ID: a178b5d2-..., Input: My subscription payment failed..., Category: billing_and_payment, Priority: high, Team: billing, Confidence: 95, Reasoning: ...
```
If there's nothing there, you'll see `No tickets routed to the <team> team.` Copy a ticket's ID from here when you need to `boost` or `flag` it.

---

## `boost` — confirm a low-confidence route was right

Use this when a ticket landed in your queue with low confidence, but it's actually classified correctly — no need to send it to admin, just vouch for it.

```
uv run cli.py boost a178b5d2-5a37-4f07-ae76-3016e7592824
```
Defaults to confidence 90. To set a specific value:
```
uv run cli.py boost a178b5d2-5a37-4f07-ae76-3016e7592824 --confidence 95
```

---

## `flag` — send a ticket to admin

Use this when a ticket in your queue is wrong — misclassified, or not actually your team's problem.

```
uv run cli.py flag eb2a5595-057d-4216-88a9-c5e5f728cfcc
```
This removes it from your team's queue and puts it in the admin queue for review.

---

## `admin-queue` — review flagged tickets

```
uv run cli.py admin-queue
```
Prints every ticket a team has flagged, so admin knows what needs correcting:
```
Ticket ID: eb2a5595-..., Input: The app crashes every time I open my account settings, Category: technical_support, Priority: high, Team: technical_support, Confidence: 90, Reasoning: ...
```

---

## `correct` — fix and re-route a flagged ticket

```
uv run cli.py correct eb2a5595-057d-4216-88a9-c5e5f728cfcc \
    --category order_issue \
    --priority high \
    --team fulfilment \
    --reasoning "Actually an order display bug, not general tech support."
```
All four flags are required: `--category`, `--priority`, `--team`, `--reasoning`. You don't need to retype the original ticket text — it's pulled automatically from the ticket's record. Once corrected, the ticket:
- leaves the admin queue,
- is set to confidence 100,
- and reappears in the **new** team's queue (`team-queue fulfilment` in this example) — not the old one.

---

## A typical end-to-end flow

```
$ uv run cli.py submit
Enter your query to be raised as a ticket: The app crashes every time I open my account settings
Ticket routed successfully: ... team=technical_support confidence=90 ...

$ uv run cli.py team-queue technical_support
Ticket ID: eb2a5595-..., ... Team: technical_support, Confidence: 90 ...

# technical_support decides this is actually an order display bug, not theirs
$ uv run cli.py flag eb2a5595-057d-4216-88a9-c5e5f728cfcc
Ticket eb2a5595-057d-4216-88a9-c5e5f728cfcc has been flagged to admin.

$ uv run cli.py admin-queue
Ticket ID: eb2a5595-..., Category: technical_support, ...

$ uv run cli.py correct eb2a5595-057d-4216-88a9-c5e5f728cfcc \
    --category order_issue --priority high --team fulfilment \
    --reasoning "Order display bug, not tech support."
Ticket eb2a5595-057d-4216-88a9-c5e5f728cfcc corrected and re-routed to fulfilment.

$ uv run cli.py team-queue fulfilment
Ticket ID: eb2a5595-..., Category: order_issue, Team: fulfilment, Confidence: 100, ...
```

## Errors you might see

- `No ticket found with id ...` — the ticket ID was mistyped or doesn't exist. Copy it exactly from a `team-queue`/`admin-queue` listing.
- `invalid Teams value: '...'` / `invalid Category value: '...'` — a typo in a flag value. Valid values are exactly the enum names shown in each command's `--help`.
- `the following arguments are required: command` — you ran `cli.py` with no subcommand. Run `uv run cli.py --help` to see the full list.
