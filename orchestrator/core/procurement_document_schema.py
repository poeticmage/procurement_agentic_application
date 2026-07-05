from pydantic import BaseModel, Field
from orchestrator.core.models import (
    Money,
    DeliveryInfo,
    FeasibilityAssessment,
    MarketRecommendation,
    VendorRecommendation,
)

class ProcurementDocument(BaseModel):
    unique_id: str
    created_at: str | None = None
    status: str = "DRAFT"

    item_name: str | None = None
    category: str | None = None
    business_purpose: str | None = None
    mandatory_specifications: list[str] = Field(default_factory=list)
    quantity: str | None = None
    unit: str | None = None

    budget_per_item: str | int | float | None = None
    total_budget: str | int | float | None = None
    feasibility: FeasibilityAssessment | None = None

    selected_option: MarketRecommendation | None = None
    vendor_recommendations: list[VendorRecommendation] = Field(default_factory=list)
    selected_vendor: str | None = None

    delivery: DeliveryInfo = Field(default_factory=DeliveryInfo)

    compliance_information: dict = Field(default_factory=dict)
    approval_requirements: dict = Field(default_factory=dict)
    procurement_method: str | None = None

    research_evidence: list[MarketRecommendation] = Field(default_factory=list)
    final_confirmed_summary: str | None = None