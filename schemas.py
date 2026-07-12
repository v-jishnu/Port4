#Enums for fixed outcomes in the support ticket system. convention : pascal case for enum names and snake case for enum values

from enum import Enum
from pydantic import BaseModel

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

class Ticket(BaseModel):
    """Pydantic model for a support ticket."""
    category: Category
    priority: Priority
    team: Teams
    description: str