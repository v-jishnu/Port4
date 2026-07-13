import asyncio
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from agents import Agent, Runner

load_dotenv()  # Loading environment variables from .env

class ValidTicket(BaseModel):
    input: str = Field(..., description="the original ticket text, verbatim, unmodified")
    is_valid: bool
    reason: str


guardrail_agent = Agent(
    name="guardrail_agent",
    instructions=(
    "Determine whether the input is a valid e-commerce support ticket. "
    "Only consider tickets related to order issues, billing and payment, "
    "product inquiries, or technical support. "
    "Also do not consider tickets that are unrelated to e-commerce support, "
    "such as general inquiries or unrelated topics, and reject tickets that "
    "are too vague, empty, or longer than 500 characters."
    ),
    output_type=ValidTicket,
    model="gpt-4o-mini",
)


async def validate_ticket(ticket_input: str)-> ValidTicket:

    # manual validation for ticket length
    if(len(ticket_input.strip()) == 0 or len(ticket_input) > 500):
        print("Invalid ticket: Ticket is either empty or too long (greater than 500 characters).")
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
    