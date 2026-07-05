from ..agents.researcher.planner_remote import planner_agent

from google.adk.tools import AgentTool

planner_agent_a2a_tool = AgentTool(agent=planner_agent)
