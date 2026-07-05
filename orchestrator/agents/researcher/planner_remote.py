from google.adk.agents.remote_a2a_agent import (
    RemoteA2aAgent,
    AGENT_CARD_WELL_KNOWN_PATH
)
from dotenv import load_dotenv

load_dotenv()

planner_agent = RemoteA2aAgent(
    name="procurement_planner",
    description="""
    Extracts procurement requirements,
    identifies missing fields,
    and returns structured procurement specifications.
    """,
    agent_card=(
        f"http://localhost:8001"
        f"{AGENT_CARD_WELL_KNOWN_PATH}"
    ),
)