from google.adk.a2a.utils.agent_to_a2a import to_a2a
from orchestrator.agents.researcher.gateway_agent import gateway_agent
from orchestrator.bootstrap_engine import engine
# from app.agents.researcher_agent.agent_card import get_agent_card
from a2a_expose.agent_executor import make_agent_executor
from a2a.types import AgentCard
import os
from a2a_expose.agent_card import get_agent_card
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
load_dotenv()
from a2a.server.tasks import DatabaseTaskStore,DatabasePushNotificationConfigStore
db_url = os.getenv("DATABASE_URL")
db_engine = create_async_engine(db_url)
task_store = DatabaseTaskStore(engine=db_engine)
push_notif_config_store = DatabasePushNotificationConfigStore(engine=db_engine)
runner = engine.runner


import logging
logger = logging.getLogger("procurement.a2a")

db_url = os.getenv("DATABASE_URL")
logger.info("a2a_expose: DATABASE_URL set=%s", bool(db_url))
if not db_url:
    logger.error("a2a_expose: DATABASE_URL missing")

try:
    db_engine = create_async_engine(db_url)
    task_store = DatabaseTaskStore(engine=db_engine)
    ...
    a2a_app = to_a2a(...)
    logger.info("a2a_expose: to_a2a() OK")
except Exception:
    logger.exception("a2a_expose: failed during startup")
    raise


a2a_app = to_a2a( 
    agent = gateway_agent,
    runner = runner,
    task_store = task_store,
    push_config_store = push_notif_config_store,
    agent_card = get_agent_card(),
    agent_executor_factory = make_agent_executor
)