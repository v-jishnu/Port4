import json

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from ticket_log import get_unified_log, get_admin_queue, get_team_queue, get_ticket_by_id, admin_correct, boost_confidence, flag_to_admin, clear_ticket
from schemas import Teams, TicketOutput, Category, Priority
from pydantic import BaseModel
from typing import Optional
from route_ticket import route_ticket, InvalidTicketError
from semantic_memory import sync_memory
from eval_harness import run_eval
from benchmark_timing import run_benchmark

app = FastAPI()


def _sync_memory_quietly() -> None:
    """Best-effort background sync after a human validates a ticket -
    a sync failure should never break the action that triggered it."""
    try:
        sync_memory()
    except Exception as e:
        print(f"Warning: background memory sync failed: {e}")

class ticket_correct(BaseModel):
    ticket_id: str
    input_text: str
    category: Category
    priority: Priority
    team: Teams
    reasoning: str

class booster(BaseModel):
    ticket_id: str
    confidence: Optional[int] = None

class NewTicket(BaseModel):
    text: str


#fetch unified log of all tickets in the system, including those that are routed, flagged, and admin corrected
@app.get("/log")
def greet():
    log = get_unified_log()
    return {"log": log}

#fetch admin queue of tickets that are flagged by teams to be routed by admin
@app.get("/admin-queue")
def get_admin_queue_endpoint():
    admin_queue = get_admin_queue()
    return {"admin_queue": admin_queue}

#fetch team queue of tickets that are routed to a specific team
@app.get("/team-queue")
def get_team_queue_endpoint(team_name: Teams):
    team_queue = get_team_queue(team_name)
    return {"team_queue": team_queue}

#fetch a specific ticket by its ID
@app.get("/ticket/{ticket_id}")
def get_ticket_by_id_endpoint(ticket_id: str):
    ticket = get_ticket_by_id(ticket_id)
    if ticket is None:
        return {"error": f"No ticket found with id {ticket_id}"}
    return {"ticket": ticket}

#admin corrects a flagged ticket, re-validates + re-routes it, then syncs semantic memory
@app.post("/route_to_admin")
def route_to_admin(ticket_output : ticket_correct):
    admin_correct(
        ticket_output.ticket_id,
        ticket_output.input_text,
        ticket_output.category,
        ticket_output.priority,
        ticket_output.team,
        ticket_output.reasoning,
    )
    _sync_memory_quietly()
    return{"message":f"{ticket_output.ticket_id} has been routed to admin"}

#confidence boosting for a low-confidence correct ticket routing, then syncs semantic memory
@app.post("/boost_confidence")
def confidence_boost(boost_conf:booster):
    if boost_conf.confidence is None:
        boost_confidence(boost_conf.ticket_id)
    else:
        boost_confidence(boost_conf.ticket_id,boost_conf.confidence)

    _sync_memory_quietly()
    return {"message":f"{boost_conf.ticket_id} ticket has been boosted"}

#a team dismisses a ticket from their active queue without deleting the record
@app.post("/clear/{ticket_id}")
def clear_ticket_endpoint(ticket_id: str):
    try:
        clear_ticket(ticket_id)
        return {"message": f"{ticket_id} cleared"}
    except Exception as e:
        return {"error": str(e)}

#fresh ticket submission via FastAPI - the actual "many mouths" entry point for route_ticket()
@app.post("/route")
async def submit_ticket(new_ticket: NewTicket):
    try:
        tck = await route_ticket(new_ticket.text)
        return tck
    except InvalidTicketError as e:
        raise HTTPException(status_code=400, detail=e.reason)

#team -> admin
@app.post("/flagged/{ticket_id}")
def flag_ticket_endpoint(ticket_id: str):
    try:
        flag_to_admin(ticket_id)
        return {"message": "flagged to admin"}
    except Exception as e:
        return {"error": str(e)}

#last saved eval baseline - fast, free, no API calls
@app.get("/eval/baseline")
def get_eval_baseline():
    try:
        with open("eval_results_baseline.json") as f:
            results = json.load(f)
    except FileNotFoundError:
        return {"passed": 0, "total": 0, "results": []}
    passed = sum(1 for r in results if r["passed"])
    return {"passed": passed, "total": len(results), "results": results}

#re-runs the eval set live - does NOT overwrite eval_results_baseline.json,
#that file is only ever updated by running eval_harness.py directly
@app.post("/eval/run")
async def run_eval_now():
    results = await run_eval()
    passed = sum(1 for r in results if r["passed"])
    return {"passed": passed, "total": len(results), "results": results}

#measures real end-to-end routing latency (before/after time comparison)
@app.post("/benchmark/run")
async def run_benchmark_now():
    average_seconds = await run_benchmark()
    return {"average_seconds": average_seconds}


# serves the frontend/ static site. Registered last so every API route above
# is matched first - this only ever catches paths none of them handle.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")