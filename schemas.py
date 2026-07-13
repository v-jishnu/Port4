#Enums for fixed outcomes in the support ticket system. convention : pascal case for enum names and snake case for enum values

from enum import Enum
from pydantic import BaseModel, Field

class Category(str, Enum):
    """Enum for category values."""
    ORDER_ISSUE = "order_issue"
    BILLING_AND_PAYMENT = "billing_and_payment"
    PRODUCT_INQUIRY = "product_inquiry"
    TECHNICAL_SUPPORT = "technical_support"

class Priority(str, Enum):
    """Enum for priority values."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Teams(str, Enum):
    """Enum for team values."""
    FULFILMENT = "fulfilment"
    BILLING = "billing"
    SALES = "sales"
    TECHNICAL_SUPPORT = "technical_support"

class TicketOutput(BaseModel):
    """Pydantic model for a support ticket."""
    input: str = Field(..., description="the original ticket text, verbatim, unmodified")
    category: Category
    priority: Priority
    team: Teams
    confidence: int = Field(..., ge=0, le=100, description="Confidence score between 0 and 100")
    reasoning: str = Field(..., description="Reasoning for LLM routing")

class HumanRouted(TicketOutput):
    """Pydantic model for human-routed tickets."""
    confidence: int = 100

print("Schemas loaded successfully.")

"""
valid_ticket = HumanRouted(
    input="my order hasn't arrived in 2 weeks",
    category=Category.ORDER_ISSUE,
    priority=Priority.HIGH,
    team=Teams.FULFILMENT,
    reasoning="Customer references a missing shipment, not a payment issue."
)
print(valid_ticket)

try:
    bad_ticket = HumanRouted(
        input="test",
        category=Category.ORDER_ISSUE,
        priority="urgent",
        team=Teams.FULFILMENT,
        reasoning="test"
    )
except Exception as e:
    print("Validation correctly failed:", e)
"""