import uuid
import os
from contextvars import ContextVar

current_session_id = str(uuid.uuid4())
APP_NAME = "procurement_agent"

_default_user_id = "user"
_default_session_id = current_session_id

_user_id: ContextVar[str] = ContextVar("user_id", default=_default_user_id)
_session_id: ContextVar[str] = ContextVar("session_id", default=_default_session_id)

# CLI / startup defaults (import-time only)
USER_ID = _default_user_id
SESSION_ID = _default_session_id
A2A_MOUNT_PATH = "/a2a/procurement_agent"
base_url = os.getenv("BASE_URL")
def set_request_ids(user_id: str | None, session_id: str | None) -> None:
    if user_id:
        _user_id.set(user_id)
    if session_id:
        _session_id.set(session_id)


def get_user_id() -> str:
    return _user_id.get()


def get_session_id() -> str:
    return _session_id.get()