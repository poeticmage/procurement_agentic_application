from google.adk.tools import AgentTool

from orchestrator.agents.researcher.email_search_agent import email_search_agent

email_search_agent_tool = AgentTool(agent=email_search_agent)