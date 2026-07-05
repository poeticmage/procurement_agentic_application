from google.adk.agents import Agent
from google.genai import Client
from google.genai import types
from ...tools.writer_tools import category_policy_tool, compliance_policy_tool
from ...tools.procurement_schema_tool import procurement_schema_tool
from ...prompts.planner_prompt import PLANNER_AGENT_PROMPT 
from dotenv import load_dotenv
from .search_agent import search_agent

load_dotenv()

planner_agent = Agent(
    name="procurement_planner",
    model="gemini-flash-lite-latest",
    description="Extracts and structures procurement requirements.",
    static_instruction=PLANNER_AGENT_PROMPT,
    sub_agents=[search_agent],
    tools=[category_policy_tool,compliance_policy_tool,procurement_schema_tool]
)



