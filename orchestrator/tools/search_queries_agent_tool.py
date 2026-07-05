from ..agents.researcher.suggested_search_query_agent import search_queries_agent

from google.adk.tools import AgentTool

search_queries_agent_tool = AgentTool(agent=search_queries_agent)
