from google.adk.agents import Agent
from orchestrator.prompts.vendor_agent_prompt import VENDOR_AGENT_PROMPT
from ...agents.researcher.negotiator_agent import negotiator_agent
from ...tools.search_tool import search_agent_tool as procurement_search_agent
from ...tools.vendor_document_tool import generate_document_tool
from ...tools.vendor_rag_tool import *
from ...core.models import VendorRecommendation



vendor_agent = Agent(
    name="vendor_selection_agent",
    model="gemini-flash-lite-latest",
    description="""
    Discovers, evaluates and shortlists vendors
    for a procurement request.
    """,
    static_instruction=VENDOR_AGENT_PROMPT,
    output_schema=list[VendorRecommendation],
    sub_agents=[negotiator_agent],
    tools=[
        vendor_rag_tool,
        list_rag_files_tool,
        get_rag_file_tool,
        replace_rag_file_tool,
        sync_vendors_tool,
        upload_rag_file_tool,
        procurement_search_agent,
        generate_document_tool
    ]
)