from google.adk.agents import Agent
from ...tools.read_json import read_json_tool 
from ...tools.write_pdf import write_pdf_report_tool
from ...prompts.procurement_report_agent_prompt import PROCUREMENT_REPORT_INSTRUCTION

procurement_report_agent = Agent(
    name="procurement_report_author_agent",
    model="gemini-flash-lite-latest",
    description="Generates a professional HTML procurement report from product JSON.",
    instruction=PROCUREMENT_REPORT_INSTRUCTION,
    tools=[read_json_tool, write_pdf_report_tool],
)