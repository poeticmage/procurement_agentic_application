from google.adk.tools import AgentTool

from ..agents.researcher.search_agent import search_agent


search_agent_tool = AgentTool(agent=search_agent)
