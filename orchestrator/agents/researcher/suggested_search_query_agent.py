from google.adk.agents import Agent
from ...core.models import SuggestedSearchQueries
from ...prompts.procurement_search_queries_agent_prmpt import search_queries_agent_prompt

search_queries_agent = Agent(
    name="procurement_search_queries_agent",
    model="gemini-flash-lite-latest",
    description="Generates high-precision ecommerce search queries for procurement search pipelines",

    static_instruction=search_queries_agent_prompt,
)