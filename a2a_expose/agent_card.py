import json
from pathlib import Path
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    HTTPAuthSecurityScheme,
    SecurityScheme,
    AgentExtension
)
 
# from app.core.config import a2a_rpc_url,portal_url
 
# _SCHEMA_DIR = Path(__file__).resolve().parents[2] / "a2a" / "schemas"
# def _load_schema(name: str) -> dict:
#     return json.loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))
# _INPUT_SCHEMA = _load_schema("researcher-input.schema.json")
# _OUTPUT_SCHEMA = _load_schema("researcher-output.schema.json")
from orchestrator.core.config import A2A_MOUNT_PATH
from orchestrator.core.config import base_url
a2a_rpc_url = f"{base_url}{A2A_MOUNT_PATH}"
def get_agent_card() -> AgentCard:
    
 
    return AgentCard(
        name="Procurement Agent",
        description=(
            "Multi-agent procurement orchestrator that collects requirements, runs market "
            "research, recommends products and vendors, generates procurement documents for "
            "approval, and coordinates post-approval vendor negotiation."
        ),
        url=a2a_rpc_url,
        version="0.0.1",
        protocolVersion="0.3.0",
        preferredTransport="JSONRPC",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=True,
        ),
        supportsAuthenticatedExtendedCard=False,
        security=[{"bearerAuth": []}],
        security_schemes={
            "bearerAuth": SecurityScheme(
                root=HTTPAuthSecurityScheme(
                    type="http",
                    scheme="Bearer",
                    description="Kong OAuth2 access token passed as Bearer token",
                )
            )
        },
        skills=[
            AgentSkill(
                id="procurement-intake",
                name="Procurement Intake",
                description=(
                    "Gathers item, quantity, budget, specifications, delivery details, and "
                    "timeline through a guided conversational workflow."
                ),
                tags=[
                    "procurement",
                    "requirements",
                    "intake",
                    "budget",
                    "delivery",
                ],
                examples=[
                    "I need 50 laptops for our Bangalore office with 16GB RAM and a total budget of 40 lakhs.",
                    "Procure ergonomic office chairs for 30 employees, delivery within 3 weeks.",
                    "We need cloud SaaS licenses for 100 users; help define specs and budget.",
                ],
            ),
            AgentSkill(
                id="vendor-sourcing",
                name="Vendor Sourcing and Selection",
                description=(
                    "Searches the market, shortlists products and vendors, applies procurement "
                    "policies, and helps the user select a final vendor."
                ),
                tags=[
                    "vendor selection",
                    "sourcing",
                    "market research",
                    "policy",
                ],
                examples=[
                    "Find Dell and HP laptop vendors near Mumbai for 50 units.",
                    "Compare three shortlisted chair suppliers and recommend the best fit.",
                    "Expand the vendor list and include local distributors.",
                ],
            ),
            AgentSkill(
                id="procurement-approval",
                name="Procurement Document and Approval",
                description=(
                    "Generates a procurement document for human review and processes "
                    "user approval before negotiation begins."
                ),
                tags=[
                    "procurement document",
                    "approval",
                    "HIL",
                    "PDF",
                ],
                examples=[
                    "Generate the procurement document for the selected vendor.",
                    "APPROVE",
                    "Reject the document and return to vendor selection.",
                ],
            ),
            AgentSkill(
                id="vendor-negotiation",
                name="Vendor Negotiation",
                description=(
                    "After document approval, discovers vendor contacts, sends RFQs, compares "
                    "offers, runs negotiation rounds with user guidance, and delivers payment "
                    "instructions for the approved vendor."
                ),
                tags=[
                    "negotiation",
                    "RFQ",
                    "email",
                    "vendor offers",
                ],
                examples=[
                    "Start negotiation with the approved vendor.",
                    "Send RFQ to all shortlisted vendors and compare quotes.",
                    "Proceed with the lowest compliant offer.",
                ],
            ),
        ],
    )