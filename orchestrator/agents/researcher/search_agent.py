from google.adk.agents import Agent
from google.adk.tools import google_search  
from ...prompts.search_agent_prompt import SEARCH_AGENT_INSTRUCTION
from ...core.models import AllSearchResults

search_agent = Agent(
    name="procurement_search_agent",
    model="gemini-flash-lite-latest",
    description="Finds and filters ecommerce product results using native Google Search",
    static_instruction= SEARCH_AGENT_INSTRUCTION,
    tools=[google_search]
    )