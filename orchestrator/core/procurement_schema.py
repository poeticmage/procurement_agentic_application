from pydantic import BaseModel, Field
from orchestrator.core.models import Money, DeliveryInfo

class ProcurementRequest(BaseModel):
    item_name: str | None = None
    category: str | None = None
    business_purpose: str | None = None
    mandatory_specifications: list[str] = Field(default_factory=list)
    optional_preferences: list[str] = Field(default_factory=list)
    quantity: str | None = None
    unit: str | None = None
    budget_per_item: str | None = None
    total_budget: str | None = None
    currency: str = "INR"
    delivery: DeliveryInfo = Field(default_factory=DeliveryInfo)
    preferred_suppliers: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)