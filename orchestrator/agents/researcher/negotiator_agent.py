
from google.adk.agents import Agent
from ...tools.email_search_agent_tool import email_search_agent_tool as vendor_email_search_tool
from ...prompts.negotiator_agent_prompt import _INSTRUCTION

##----------------------------------
##------------------------------------  
##------------------------------------  
##------------------------------------  
from google.adk.tools import FunctionTool
import requests

EMAIL_AGENT_URL = "https://devallyraadkemailagent.pansophictech.com/email/agent"

def email_agent_tool(
    prompt: str,
    user_id: str,
    organization_id: str,
    session_id: str,
    agent_id: str,
) -> str:
    payload = {
        "user_id": user_id,
        "prompt": prompt,
        "organization_id": organization_id,
        "session_id": session_id,
        "agent_id": agent_id,
        "attachments": [],
        "filters": {
            "accounts": "all"
        }
    }

    response = requests.post(
        EMAIL_AGENT_URL,
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    return response.text


email_tool = FunctionTool(email_agent_tool)

##----------------------------------------------------------    --  
##----------------------------------------------------------    --  
##----------------------------------------------------------    --  
##----------------------------------------------------------    --  



# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

negotiator_agent = Agent(
    name="negotiator_agent",
    model="gemini-flash-lite-latest",
    description=(
        "Handles the complete vendor negotiation lifecycle after procurement "
        "document approval. Discovers vendor emails, dispatches RFQs, collects "
        "and compares offers, conducts negotiation rounds with explicit user "
        "approval at every step, and delivers structured payment instructions "
        "for the user-approved vendor."
    ),
    static_instruction=_INSTRUCTION,
    # disallow_transfer_to_peers=False,
    tools=[
        vendor_email_search_tool, email_tool
        
    ],
)