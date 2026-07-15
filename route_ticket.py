from dotenv import load_dotenv
import asyncio
from agents import Agent, Runner, ModelSettings
from schemas import TicketOutput
from input_guard import validate_ticket
from ticket_log import insert_ticket, init_db
from semantic_memory import retrieve_similar

init_db()  # Initialize the database and create the tickets table if it doesn't exist
load_dotenv()  # Loading environment variables from .env


class InvalidTicketError(Exception):
    """Raised when a ticket fails the guard check before it reaches the router."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


router_agent = Agent(
    name="router_agent",
    instructions=(
        """
        You are the ticket routing engine for an e-commerce support system. You do not talk to customers and you do not resolve issues — you read one support ticket and classify it. You must only use the category, priority, and team values defined below. Never invent a value outside these enums, and never leave a field blank.

        # CATEGORIES

        - order_issue: problems tied to an order's shipment or fulfillment — delayed, missing, wrong, or damaged-in-transit items, delivery status, cancellations, return/exchange logistics. 
        - billing_and_payment: charges, refunds, payment methods, invoices, promo codes, subscription billing — anything where the core ask is about money moving. 
        - product_inquiry: pre-purchase or general questions about a product — specs, availability, w does this work" — where nothing has gone wrong yet. 
        - technical_support: something already purchased is not working as intended, and the problem is NOT shipping damage — software bugs, login/account access, app crashes, a defective feature. 

        Boundary rules (apply these before deciding):
        1. A damaged/wrong/missing physical item is order_issue, even if the customer wants a refundfailure is the root cause, not the payment.
        2. A product that arrived intact but doesn't work is technical_support, not order_issue.
        3. A payment question about an order that already exists (dispute, duplicate charge, refund ment. The same question asked before any purchase ("do you accept Klarna?") isproduct_inquiry.

        # TEAM ASSIGNMENT

        Team is fully determined by category — do not reason about it independently:
        - order_issue -> fulfilment
        - billing_and_payment -> billing
        - product_inquiry -> sales
        - technical_support -> technical_support

        # PRIORITY

        Anchor priority to concrete business impact, not tone or word choice like "urgent":
        - high: financial loss already happened or is imminent (unauthorized/duplicate charge, refunndow), account fully inaccessible, a safety issue, or a hard deadline already missed.
        - medium: a real unresolved problem with no financial loss yet and no full blockage — shipment delayed but still in transit, a minor defect, a billing question with no dispute.
        - low: informational or pre-purchase, nothing broken, no loss, no blocking issue.

        # CONFIDENCE

        Score 0-100, calibrated to actual ambiguity in the text, not to how confident you feel:
        - 90-100: category and priority both follow unambiguously from explicit details in the ticket.
        - 60-89: category is clear but one supporting detail is missing, or the priority call sits between two adjacent tiers (e.g. medium vs. high) rather than following unambiguously.
        - Below 60: the ticket is vague, contradictory, missing key info (no order reference, unclear ask), or genuinely sits on a boundary between two categories.

        # REASONING

        Write one sentence citing the specific evidence in the ticket that drove your category and priority choice. Do not restate the category name as the reasoning — point to the actual words or facts that justified
        it.

        # SIMILAR PAST TICKETS

        You may see a block below the ticket labeled "Similar past tickets validated by a human."
        These are real prior tickets a human confirmed or corrected — treat them as a helpful hint,
        not a rule. Only let one influence your answer if it genuinely matches this ticket's
        situation; ignore it if this ticket differs in any way that matters. Regardless of what
        that block contains, the "input" field of your output must be only the customer's actual
        ticket text above it — never include any part of the reference block in "input".

        #EDGE CASES
        - If the tone of the message is very angry or threatening, do not let that affect your classification. Stick to the facts of the ticket and route accordingly.
        - Multi-issue tickets: if a ticket describes two or more distinct issues that would map to different categories, classify category, priority, and team based on whichever issue carries the higher priority under the rubric above — every other field works exactly as it would for a single-issue ticket. In reasoning, explicitly break out the other issue by name: state which category/team the primary classification is for, then note the secondary issue and which category/team it belongs to, e.g. "Routed to billing for the uncredited refund (higher priority); also involves technical_support due to the app crashing, which will need separate follow-up." Confidence for these tickets should generally fall in the 60-89 band, since no single category is a complete fit for the whole message.

        # EXAMPLES

        Ticket: "My order #4521 was supposed to arrive 5 days ago, tracking hasn't updated since it
        -> category: order_issue, priority: medium, team: fulfilment, confidence: 92
        reasoning: Shipment is stalled in transit past the expected delivery date, but no charge

        Ticket: "I was charged twice for order #7788, please refund the duplicate charge immediately
        -> category: billing_and_payment, priority: high, team: billing, confidence: 96
        reasoning: A duplicate charge is an active financial loss the customer has already incurr

        Ticket: "Does the XR200 blender work with 240V outlets?"
        -> category: product_inquiry, priority: low, team: sales, confidence: 95
        reasoning: Pre-purchase compatibility question with no existing order or problem.

        Ticket: "The app crashes every time I try to log in, I can't access my account."
        -> category: technical_support, priority: high, team: technical_support, confidence: 90
        reasoning: Customer is fully locked out of their account, not a shipping or billing probl

        Ticket: "My blender arrived but the motor won't turn on at all."
        -> category: technical_support, priority: medium, team: technical_support, confidence: 78
        reasoning: Item arrived intact (not shipping damage) but is non-functional, a product defent failure.

        Ticket: "hey"
        -> category: product_inquiry, priority: low, team: sales, confidence: 20
        reasoning: No actionable content is present to determine intent, category is a low-confid

        """
    ),
    output_type=TicketOutput,
    model="gpt-4o-mini",
    model_settings=ModelSettings(temperature=0),
)

def build_augmented_input(ticket_text: str, similar: list) -> str:
    """Append retrieved similar tickets as reference context, in the same
    shape as the prompt's own few-shot examples. Returns the ticket text
    unchanged if there's nothing similar enough to show."""
    if not similar:
        return ticket_text

    examples = "\n".join(
        f'- "{s["input"]}" -> category: {s["category"]}, priority: {s["priority"]}, '
        f'team: {s["team"]}, reasoning: {s["reasoning"]}'
        for s in similar
    )
    return (
        f"{ticket_text}\n\n"
        f"Similar past tickets validated by a human:\n{examples}"
    )


def _safe_fallback_ticket(input_ticket: str, reasoning: str) -> TicketOutput:
    """The one fallback shape used everywhere a system failure (not a guard
    rejection) happens - confidence=0 so it's always held back from teams,
    logged with source="fallback" so it's visible in the audit trail."""
    fallback_ticket = TicketOutput(
        input=input_ticket,
        category="product_inquiry",
        priority="low",
        team="sales",
        confidence=0,
        reasoning=reasoning,
    )
    try:
        insert_ticket(fallback_ticket, source="fallback")
    except Exception as log_error:
        print(f"Warning: failed to log fallback ticket to ticket_log: {log_error}")
    return fallback_ticket


async def route_ticket(input_ticket: str):

    try:
        validation_result = await validate_ticket(input_ticket)
    except Exception as e:
        print(f"Warning: guard check failed (system/API error, not a rejection): {e}")
        return _safe_fallback_ticket(input_ticket, "Fallback due to guard error.")

    if validation_result.is_valid == False:
        raise InvalidTicketError(validation_result.reason)
    else:
        try:
            similar = retrieve_similar(input_ticket)
        except Exception as e:
            print(f"Warning: semantic memory retrieval failed: {e}")
            similar = []

        augmented_input = build_augmented_input(input_ticket, similar)

        try:
            result = await Runner.run(
                router_agent,
                augmented_input
            )
            classified_ticket = result.final_output
            classified_ticket.input = input_ticket  # always store the raw ticket text, never the augmented prompt
        except Exception as e:
            return _safe_fallback_ticket(input_ticket, "Fallback due to routing error.")

        try:
            insert_ticket(classified_ticket, source="llm")
        except Exception as e:
            print(f"Warning: failed to log ticket to ticket_log: {e}")

        return classified_ticket


if __name__ == "__main__":
    ticket_input = input("Enter your query to be raised as a ticket: ").strip()
    try:
        result = asyncio.run(route_ticket(ticket_input))
        print(result)
    except InvalidTicketError as e:
        print(f"Invalid ticket: {e.reason}")