from google.adk.agents import Agent
from ...core.models import AllExtractedProducts
from orchestrator.tools.scrapping_tool import web_scraping_tool
from orchestrator.tools.read_json import read_json_tool
from orchestrator.prompts.scrapper_agent_prompt import SCRAPPER_AGENT_INSTRUCTION

scraper_agent = Agent(
    name="procurement_scraper_agent",
    model="gemini-flash-lite-latest",

    description="Extracts structured product data from ecommerce pages using web scraping",

    instruction=SCRAPPER_AGENT_INSTRUCTION,

    tools=[web_scraping_tool, read_json_tool],
)