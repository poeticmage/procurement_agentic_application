from google.adk.agents import Agent
from orchestrator.tools.procurement_workflow_tool import procurement_workflow_tool


gateway_agent = Agent(
    name="procurement_gateway",
    model="gemini-2.5-flash",
    tools=[
        procurement_workflow_tool
    ],
    instruction="""
    Always invoke procurement_workflow_tool.
    Never answer directly.
    """
)