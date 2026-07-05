from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.sessions import DatabaseSessionService
from orchestrator.core.config import  APP_NAME, USER_ID, SESSION_ID
from orchestrator.core.config import get_user_id, get_session_id

from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
import logging
logger = logging.getLogger("procurement.engine")


class ProcurementEngine:
    def __init__(self, app):
        self.session_service = DatabaseSessionService(
            db_url=DATABASE_URL
        )
        self.session = None

        self.runner = Runner(
            app=app,
            app_name=APP_NAME,
            session_service=self.session_service,
            auto_create_session=True
        )

    async def init_session(self):
        self.session = await self.session_service.create_session(
            app_name=APP_NAME,
            user_id=get_user_id(),
            session_id=get_session_id()
        )

    