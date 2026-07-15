from fastapi import FastAPI, HTTPException
from ticket_log import get_unified_log, get_admin_queue, get_team_queue, get_ticket_by_id, admin_correct, boost_confidence, flag_to_admin
from schemas import Teams, TicketOutput, Category, Priority
from pydantic import BaseModel
from typing import Optional
from route_ticket import route_ticket, InvalidTicketError
app = FastAPI()

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

#route a ticket to admin
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
    return{"message":f"{ticket_output.ticket_id} has been routed to admin"}

#confidence boosting for a low-confidence correct ticket routing
@app.post("/boost_confidence")
def confidence_boost(boost_conf:booster):
    if boost_conf.confidence is None:
        boost_confidence(boost_conf.ticket_id)
    else:
        boost_confidence(boost_conf.ticket_id,boost_conf.confidence)
    
    return {"message":f"{boost_conf.ticket_id} ticket has been boosted"}

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