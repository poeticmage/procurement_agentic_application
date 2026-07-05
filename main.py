import os
from dotenv import load_dotenv
import asyncio
import logging
from orchestrator.bootstrap_engine import engine
from orchestrator.agents.researcher.root import app
from orchestrator.core.workflow_state import WorkflowState
from orchestrator.core.procurement_context import ProcurementContext
from orchestrator.core.config import *
from orchestrator.agents.handler import *
from vertexai.preview import rag
from services.vendor_rag_services import VendorRagService
import json 
import base64
from orchestrator.core.config import A2A_MOUNT_PATH
from google.oauth2 import service_account
from orchestrator.core.config import set_request_ids
import vertexai
from a2a_expose.app import a2a_app
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from a2a_expose.agent_card import get_agent_card
from typing import Any
load_dotenv()
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("procurement.startup")
logger.info("main.py: load_dotenv done")
#------------------------------------------------------------------------------------------------
import logging
import time
import json
from pathlib import Path
from starlette.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette._utils import get_route_path
from services.kong_auth_service import verify_kong_token, KongAuthError
kong_admin_url = os.getenv("KONG_ADMIN_URL")
PUBLIC_PATHS={
    "/.well-known/agent.json",
    "/.well-known/agent-card.json",
    f"{A2A_MOUNT_PATH}/.well-known/agent.json",
    f"{A2A_MOUNT_PATH}/.well-known/agent-card.json",
}
class StripPrefixMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, prefix: str):
        super().__init__(app)
        self.prefix = prefix.rstrip("/")
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == self.prefix or path.startswith(f"{self.prefix}/"):
            request.scope["path"] = path[len(self.prefix) :] or "/"
        return await call_next(request)
 
def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
 
 
class KongAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        path = get_route_path(request.scope)
        method = request.method
        client_ip = _client_ip(request)
        auth_result = "ok"
 
        if not kong_admin_url:
            auth_result = "kong_not_configured"
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.error(
                "http_request method=%s path=%s client_ip=%s status=%s "
                "auth_result=%s duration_ms=%s",
                method, path, client_ip, 500, auth_result, duration_ms,
            )
            return JSONResponse(
                {"detail": "Kong auth not configured"},
                status_code=500,
            )
 
        if path in PUBLIC_PATHS:
            auth_result = "public_path"
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "http_request method=%s path=%s client_ip=%s status=%s "
                "auth_result=%s duration_ms=%s",
                method, path, client_ip, response.status_code,
                auth_result, duration_ms,
            )
            return response
 
        token = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.removeprefix("Bearer ").strip()
 
        if not token:
            auth_result = "missing_token"
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "http_request method=%s path=%s client_ip=%s status=%s "
                "auth_result=%s duration_ms=%s",
                method, path, client_ip, 401, auth_result, duration_ms,
            )
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
 
        try:
            await verify_kong_token(token, kong_admin_url=kong_admin_url)
            auth_result = "kong_ok"
        except KongAuthError as exc:
            auth_result = "invalid_token"
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "http_request method=%s path=%s client_ip=%s status=%s "
                "auth_result=%s duration_ms=%s",
                method, path, client_ip, exc.status_code, auth_result, duration_ms,
            )
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
 
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "http_request method=%s path=%s client_ip=%s status=%s "
            "auth_result=%s duration_ms=%s",
            method, path, client_ip, response.status_code,
            auth_result, duration_ms,
        )
        logger.info("startup: initializing Vertex AI...")
        try:
            if "GOOGLE_SERVICE_ACCOUNT_BASE64" not in os.environ:
                logger.error("GOOGLE_SERVICE_ACCOUNT_BASE64 not set")
                raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_BASE64 not set")
            service_account_info = json.loads(
                base64.b64decode(os.environ["GOOGLE_SERVICE_ACCOUNT_BASE64"]).decode("utf-8")
            )
            credentials = service_account.Credentials.from_service_account_info(service_account_info)
            vertexai.init(
                project=os.getenv("VERTEX_AI_RAG_PROJECT_ID"),
                location=os.getenv("VERTEX_AI_RAG_LOCATION"),
                credentials=credentials,
            )
            logger.info("startup: vertexai.init OK project=%s", os.getenv("VERTEX_AI_RAG_PROJECT_ID"))
        except Exception:
            logger.exception("startup: Vertex AI init failed")
            raise
        return response


#------------------------------------------------------------------------------------------------

service_account_info = json.loads(
    base64.b64decode(
        os.environ["GOOGLE_SERVICE_ACCOUNT_BASE64"]
    ).decode("utf-8")
)
    
    
credentials = service_account.Credentials.from_service_account_info(
    service_account_info
)

vertexai.init(
    project=os.getenv("VERTEX_AI_RAG_PROJECT_ID"),
    location=os.getenv("VERTEX_AI_RAG_LOCATION"),
    credentials=credentials,
)
#------------------------------------------------------------------------------------------------





context = ProcurementContext()
context.user_id = USER_ID
context.session_id = SESSION_ID

# rag_service = VendorRagService()
# files = rag_service.list_files()
# print(f"Corpus reachable. Files found: {len(files)}")
# for idx, file in enumerate(files, start=1):
#     print(f"\n[{idx}]")
#     print(file)
# print("========== RAG CHECK PASSED ==========\n")



async def main():
    await engine.init_session()
    runner = engine.runner
    print("Procurement system started. What do you want?\n")
    # print(dir(rag))
    while True:
        try:
            text = await asyncio.to_thread(input, "You: ")

            if not text:
                continue

            if context.state in {
                WorkflowState.INTENT_ITEM,
                WorkflowState.INTENT_CATEGORY,
                WorkflowState.INTENT_PURPOSE,
                WorkflowState.INTENT_SPECS,
                WorkflowState.QUANTITY,
                WorkflowState.BUDGET_PER_ITEM,
                WorkflowState.BUDGET_TOTAL,
                WorkflowState.BUDGET_CONFIRMATION,
                WorkflowState.MARKET_RESEARCH,
                WorkflowState.FEASIBILITY_REVIEW,
                WorkflowState.RECOMMENDATION_REVIEW,
                WorkflowState.RECOMMENDATION_REFINEMENT,
                WorkflowState.SELECTION_CONFIRMATION,
                WorkflowState.DELIVERY_TIMELINE,
                WorkflowState.DELIVERY_ADDRESS,
                WorkflowState.DELIVERY_CITY,
                WorkflowState.DELIVERY_STATE,
                WorkflowState.DELIVERY_COUNTRY,
                WorkflowState.DELIVERY_POSTAL_CODE,
                WorkflowState.DELIVERY_CONTACT,
                WorkflowState.DELIVERY_CONFIRMATION,
                WorkflowState.DELIVERY_CONFIRMATION,
                WorkflowState.VENDOR_REVIEW,
                WorkflowState.VENDOR_EXPANSION,
                
            }:
                await handle_state_input(text, context, runner)

            elif context.state == WorkflowState.FEASIBILITY_ASSESSMENT:
                handle_feasibility_assessment(context)

            elif context.state == WorkflowState.VENDOR_POLICY_EVALUATION:
                await handle_state_input(text, context, runner)

            # elif context.state == WorkflowState.FINAL_DOCUMENT_DRAFT:
            #     handle_final_document_draft(context)

            # elif context.state == WorkflowState.COMPLETE:
            #     handle_complete(text,context)

            # elif context.state == WorkflowState.NEGOTIATION_COMPLETE:
            #     await handle_negotiation_complete(text,context,runner)

        except KeyboardInterrupt:
            print("\nSession terminated.")
            break

        except Exception as e:
            print("Runtime error:", e)


if __name__ == "__main__":
    asyncio.run(main())
    print("\n========== RAG STARTUP CHECK ==========")
    try:
        rag_service = VendorRagService()
        files = rag_service.list_files()
        print(f"Corpus reachable. Files found: {len(files)}")
        for idx, file in enumerate(files, start=1):
            print(f"\n[{idx}]")
            print(file)
        print("========== RAG CHECK PASSED ==========\n")
    except Exception as e:
        print("\n========== RAG CHECK FAILED ==========")
        print(str(e))
        print("=====================================\n")
        raise






import os
import json
import base64
import re
import builtins
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from google.oauth2 import service_account
import vertexai
# from main import engine,context
from orchestrator.agents.researcher.root import app as agent_app
from orchestrator.core.workflow_state import WorkflowState
from google.genai.errors import ClientError   # ← add this
from orchestrator.core.config import USER_ID, SESSION_ID
from orchestrator.agents.handler import (
    handle_state_input,
    handle_feasibility_assessment,
    handle_final_document_draft,
    handle_complete,
    handle_negotiation_complete,
)

load_dotenv()

latest_response:str|None=None
tokens: dict | None = None
agents_tools: list[str] = []
clean_message: str | None = None


async def check_database() -> dict[str, Any]:
    url = os.getenv("DATABASE_URL")
    if not url:
        return {"ok": False, "error": "DATABASE_URL not set"}
    db_engine = create_async_engine(url)
    try:
        async with db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        await db_engine.dispose()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("lifespan: start")
    global latest_response, clean_message
    await engine.init_session()
    latest_response = "Procurement system started. What do you want?"
    clean_message = latest_response
    async with a2a_app.router.lifespan_context(a2a_app):
            yield

app=FastAPI(lifespan=lifespan)


def _gemini_error_reason(exc: ClientError) -> str | None:
    if not isinstance(exc.details, dict):
        return None
    for item in exc.details.get("error", {}).get("details") or []:
        if isinstance(item, dict) and item.get("reason"):
            return item["reason"]
    return None
@app.exception_handler(ClientError)
async def handle_gemini_client_error(request: Request, exc: ClientError):
    payload = {
        "detail": f"Gemini API error: {exc.message or str(exc)}",
        "gemini_code": exc.code,
        "gemini_status": exc.status,
        "gemini_reason": _gemini_error_reason(exc),
    }
    logger.error(
        "Gemini API request failed path=%s code=%s status=%s reason=%s message=%s",
        request.url.path,
        exc.code,
        exc.status,
        payload["gemini_reason"],
        exc.message,
    )
    return JSONResponse(status_code=502, content=payload)
logger.info("startup: FastAPI app created")

logger.info("startup: FastAPI app created")


class MessageRequest(BaseModel):
    text:str
    user_id: str | None = None
    session_id: str | None = None
    organization_id: str | None = None

class AssistantResponse(BaseModel):
    state: str
    tokens: dict | None = None
    agents_tools: list[str] | None = None
    message: str | None = None

ACTIVE_STATES = {
    WorkflowState.INTENT_ITEM, WorkflowState.INTENT_CATEGORY,
    WorkflowState.INTENT_PURPOSE, WorkflowState.INTENT_SPECS,
    WorkflowState.QUANTITY, WorkflowState.BUDGET_PER_ITEM,
    WorkflowState.BUDGET_TOTAL, WorkflowState.BUDGET_CONFIRMATION,
    WorkflowState.MARKET_RESEARCH, WorkflowState.FEASIBILITY_REVIEW,
    WorkflowState.RECOMMENDATION_REVIEW, WorkflowState.RECOMMENDATION_REFINEMENT,
    WorkflowState.SELECTION_CONFIRMATION, WorkflowState.DELIVERY_TIMELINE,
    WorkflowState.DELIVERY_ADDRESS, WorkflowState.DELIVERY_CITY,
    WorkflowState.DELIVERY_STATE, WorkflowState.DELIVERY_COUNTRY,
    WorkflowState.DELIVERY_POSTAL_CODE, WorkflowState.DELIVERY_CONTACT,
    WorkflowState.DELIVERY_CONFIRMATION, WorkflowState.VENDOR_REVIEW,
     WorkflowState.VENDOR_EXPANSION,
     WorkflowState.VENDOR_POLICY_EVALUATION,
    
}
_contexts: dict[str, ProcurementContext] = {}

def get_procurement_context(user_id: str, session_id: str) -> ProcurementContext:
    if session_id not in _contexts:
        ctx = ProcurementContext()
        ctx.user_id = user_id
        ctx.session_id = session_id
        _contexts[session_id] = ctx
    return _contexts[session_id]

@app.post("/chat", response_model=AssistantResponse)
async def send_message(req:MessageRequest):
    set_request_ids(req.user_id, req.session_id)
    ctx = get_procurement_context(req.user_id, req.session_id)
    global latest_response, tokens, agents_tools, clean_message
    text=req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    captured_lines:list[str]=[]
    original_print=builtins.print
    builtins.print = lambda *args, **kwargs: captured_lines.append(" ".join(str(a) for a in args))

    try:
        if ctx.state in ACTIVE_STATES:
            await handle_state_input(text, ctx, engine.runner)
        elif ctx.state == WorkflowState.FEASIBILITY_ASSESSMENT:
            handle_feasibility_assessment(ctx)
        # elif context.state == WorkflowState.FINAL_DOCUMENT_DRAFT:
        #     handle_final_document_draft(context)
        # elif context.state == WorkflowState.COMPLETE:
        #     handle_complete(text, context)
        # elif context.state == WorkflowState.NEGOTIATION_COMPLETE:
        #     await handle_negotiation_complete(text, context, engine.runner)
    finally:
        builtins.print = original_print
    latest_response="\n".join(captured_lines) or None
    tokens = None
    agents_tools = []
    clean_message = None
    if latest_response:
        prompt_match = re.search(r"Prompt tokens:\s*(\d+)", latest_response)
        completion_match = re.search(r"Completion tokens:\s*(\d+)", latest_response)
        total_match = re.search(r"Total tokens:\s*(\d+)", latest_response)

        if prompt_match and completion_match and total_match:
            tokens = {
                "prompt": int(prompt_match.group(1)),
                "completion": int(completion_match.group(1)),
                "total": int(total_match.group(1)),
            }

        for line in latest_response.splitlines():
            if line.startswith("Agent:"):
                agents_tools.append(line.replace("Agent: ", "").strip())
            if line.startswith("Tool Name : "):
                agents_tools.append(line.replace("Tool Name: ", "").strip())
        clean_message = latest_response

        if clean_message:
            clean_message = re.sub(r"Agent:.*\n?", "", clean_message)
            clean_message = re.sub(r"Prompt tokens:.*\n?", "", clean_message)
            clean_message = re.sub(r"Completion tokens:.*\n?", "", clean_message)
            clean_message = re.sub(r"Total tokens:.*\n?", "", clean_message)
            clean_message = clean_message.strip()
    return AssistantResponse(
        state=ctx.state.value,
        tokens=tokens,
        agents_tools=agents_tools,
        message=clean_message,
    )



@app.get("/health")
async def health():
    result = await check_database()
    if result.get("ok"):
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "database": result},
        )
    return JSONResponse(
        status_code=503,
        content={"status": "error", "database": result},
    )
# @app.get("/response",response_model=AssistantResponse)
# async def get_response():
#     return AssistantResponse(state=context.state.value,tokens=tokens,agents_tools=agents_tools,message=clean_message)

# @app.get("/state")
# async def get_state():
#     return {"state":context.state.value}




# --------------- A2A EXPOSE ---------------

@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
async def root_agent_card():
    card = get_agent_card()
    return JSONResponse(status_code=200, content=card.model_dump(mode="json"))

# Kong auth only on A2A routes (sub-app sees paths without mount prefix)
a2a_app.add_middleware(KongAuthMiddleware)
app.mount(A2A_MOUNT_PATH, a2a_app)

logger.info("startup: A2A mounted at %s — module import finished", A2A_MOUNT_PATH)
