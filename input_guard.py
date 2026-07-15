import asyncio
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from agents import Agent, Runner, ModelSettings

load_dotenv()  # Loading environment variables from .env

class ValidTicket(BaseModel):
    input: str = Field(..., description="the original ticket text, verbatim, unmodified")
    is_valid: bool
    reason: str


guardrail_agent = Agent(
    name="guardrail_agent",
    instructions=(
    "Determine whether the input is a valid e-commerce support ticket. "
    "Accept tickets in any of these four categories: order issues (shipping, delivery, returns, "
    "cancellations); billing and payment (charges, refunds, invoices, promo codes); product "
    "inquiries (questions about a specific product's specs, sizing, availability, shipping "
    "destinations, or accepted payment methods — these are valid tickets even when phrased as a "
    "simple pre-purchase question and nothing has gone wrong yet); or technical support (something "
    "not working as intended). "
    "Only reject a ticket for being unrelated if it has no connection at all to a store, product, "
    "order, or payment — e.g. small talk, topics with no link to e-commerce, or spam. Do not reject "
    "a ticket just because it sounds like a general question — a product inquiry is a valid ticket "
    "on its own, it does not also need to resemble an order, billing, or technical issue. "
    "Reject a ticket as too vague only when it has no identifiable product, order, or issue to act "
    "on (e.g. 'this' or 'my stuff' with nothing named), or if it is empty or longer than 500 characters."
    ),
    output_type=ValidTicket,
    model="gpt-4o-mini",
    model_settings=ModelSettings(temperature=0),
)


async def validate_ticket(ticket_input: str)-> ValidTicket:

    # manual validation for ticket length
    if(len(ticket_input.strip()) == 0 or len(ticket_input) > 500):
        return ValidTicket(input=ticket_input, is_valid=False, reason="Ticket is either empty or too long.")

    
    result = await Runner.run(
        guardrail_agent,
        ticket_input
    )

    return result.final_output

if __name__ == "__main__":
    ticket_input = input("Enter your query to be raised as a ticket: ")
    outcome = asyncio.run(validate_ticket(ticket_input))
    print(outcome)
    