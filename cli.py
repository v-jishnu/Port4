import argparse
from ticket_log import flag_to_admin, boost_confidence

parser = argparse.ArgumentParser(description="Flag a ticket to admin.")
subparser = parser.add_subparsers(dest="command" , required=True)

# team -> admin routing
flag_parser = subparser.add_parser("flag", help="Flag a ticket to admin.")
flag_parser.add_argument("ticket_id", help="The ID of the ticket to flag.")

#confidence boost to correct a low-confidence route
boost_parser = subparser.add_parser("boost", help="Boost the confidence of a ticket.")
boost_parser.add_argument("ticket_id", help="The ID of the ticket to boost.")
boost_parser.add_argument("--confidence", type=int, default=90, help="The new confidence level (0-100). Default is 90.")





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