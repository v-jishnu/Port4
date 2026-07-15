import argparse
import asyncio
from ticket_log import flag_to_admin, boost_confidence, get_admin_queue, get_team_queue, get_ticket_by_id, admin_correct
from route_ticket import route_ticket
from schemas import Category, Priority, Teams, TicketOutput

parser = argparse.ArgumentParser()
subparser = parser.add_subparsers(dest="command" , required=True)

# team -> admin routing
flag_parser = subparser.add_parser("flag", help="Flag a ticket to admin.")
flag_parser.add_argument("ticket_id", help="The ID of the ticket to flag.")

#confidence boost to correct a low-confidence route
boost_parser = subparser.add_parser("boost", help="Boost the confidence of a ticket.")
boost_parser.add_argument("ticket_id", help="The ID of the ticket to boost.")
boost_parser.add_argument("--confidence", type=int, default=90, help="The new confidence level (0-100). Default is 90.")

#manual cli based ticket input to call routing function like __main__
route_parser = subparser.add_parser("submit", help="Route a ticket through the system.")
route_parser.add_argument("ticket_input_text", help="The ticket input text to route.")

#Admin queue for flagged tickets to be routed by admin
#seperate subparser for admin queue to view tickets flagged by teams as param is optional and not required 
admin_ticket_parser = subparser.add_parser("admin-queue", help="Shows the tickets flagged to admin for routing.")

#team ticket views
team_queue_parser = subparser.add_parser("team-queue", help="View tickets routed to a specific team.")
team_queue_parser.add_argument("team_name", type=Teams, help="The name of the team to view tickets for. Options: technical_support, sales, billing, shipping.")

#admin correction of a flagged ticket, re-routes it and validates via HumanRouted
correct_parser = subparser.add_parser("correct", help="Admin corrects a flagged ticket.")
correct_parser.add_argument("ticket_id", help="The ID of the ticket to correct.")
correct_parser.add_argument("--category", type=Category, required=True, help="Corrected category.")
correct_parser.add_argument("--priority", type=Priority, required=True, help="Corrected priority.")
correct_parser.add_argument("--team", type=Teams, required=True, help="Corrected team.")
correct_parser.add_argument("--reasoning", required=True, help="Corrected reasoning.")

args = parser.parse_args()
# confidence boost for tickets that are routed incorrectly due to low confidence
if args.command == "boost":
    try:
        boost_confidence(args.ticket_id , new_confidence=args.confidence)
        print(f"Confidence for ticket {args.ticket_id} has been boosted.")
    except Exception as e:
        print(f"Error boosting confidence for ticket {args.ticket_id}: {e}")

# admin routing for tickets that are flagged by teams
if args.command == "flag":
    try:
        flag_to_admin(args.ticket_id)
        print(f"Ticket {args.ticket_id} has been flagged to admin.")
    except Exception as e:
        print(f"Error flagging ticket {args.ticket_id}: {e}")

# manual routing of tickets through the system
if args.command == "submit":
    try:
        result = asyncio.run(route_ticket(args.ticket_input_text))
        print(f"Ticket routed successfully: {result}")
    except Exception as e:
        print(f"Error routing ticket: {e}")

# admin queue for tickets that are flagged by teams to be routed by admin
if args.command == "admin-queue":
    try:
        admin_queue = get_admin_queue()
        if not admin_queue:
            print("No tickets in the admin queue.")
        else:
            for ticket in admin_queue:
                print(f"Ticket ID: {ticket['id']}, Input: {ticket['input']}, Category: {ticket['category']}, Priority: {ticket['priority']}, Team: {ticket['team']}, Confidence: {ticket['confidence']}, Reasoning: {ticket['reasoning']}")
    except Exception as e:
        print(f"Error retrieving admin queue: {e}")

# team queue for tickets that are routed to a specific team
if args.command == "team-queue":
    try:
        team_queue = get_team_queue(args.team_name)
        if not team_queue:
            print(f"No tickets routed to the {args.team_name} team.")
        else:
            for ticket in team_queue:
                print(f"Ticket ID: {ticket['id']}, Input: {ticket['input']}, Category: {ticket['category']}, Priority: {ticket['priority']}, Team: {ticket['team']}, Confidence: {ticket['confidence']}, Reasoning: {ticket['reasoning']}")
    except Exception as e:
        print(f"Error retrieving team queue for {args.team_name}: {e}")

# admin corrects a flagged ticket and re-routes it to the right team
if args.command == "correct":
    try:
        ticket = get_ticket_by_id(args.ticket_id)
        if ticket is None:
            print(f"No ticket found with id {args.ticket_id}")
        else:
            admin_correct(
                args.ticket_id,
                input_text=ticket["input"],
                category=args.category,
                priority=args.priority,
                team=args.team,
                reasoning=args.reasoning,
            )
            print(f"Ticket {args.ticket_id} corrected and re-routed to {args.team.value}.")
    except Exception as e:
        print(f"Error correcting ticket {args.ticket_id}: {e}")