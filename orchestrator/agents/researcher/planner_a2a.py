from google.adk.a2a.utils.agent_to_a2a import to_a2a
from .planner import planner_agent
from dotenv import load_dotenv

load_dotenv()

a2a_app = to_a2a(
    planner_agent,
    port=8001
)