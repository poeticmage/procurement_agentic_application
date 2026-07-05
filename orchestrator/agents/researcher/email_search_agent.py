from google.adk.agents import Agent
from google.adk.tools import google_search  
from ...prompts.email_search_agent_instructions import EMAIL_SEARCH_AGENT_INSTRUCTION
from ...core.models import AllSearchResults

email_search_agent = Agent(
    name="email_search_agent",
    model="gemini-flash-lite-latest",
    description="Finds and filters ecommerce product results using native Google Search",
    static_instruction= EMAIL_SEARCH_AGENT_INSTRUCTION,
    tools=[google_search]
    )