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
from main import engine,context
from orchestrator.agents.researcher.root import app as agent_app
from orchestrator.core.workflow_state import WorkflowState
from orchestrator.core.config import USER_ID, SESSION_ID
from orchestrator.agents.handler import (
    handle_state_input,
    handle_feasibility_assessment,
    handle_final_document_draft,
    handle_complete,
)

load_dotenv()

latest_response:str|None=None
tokens: dict | None = None
agents_tools: list[str] = []
clean_message: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global latest_response, clean_message
    await engine.init_session()
    latest_response = "Procurement system started. What do you want?"
    clean_message = latest_response
    yield

api=FastAPI(lifespan=lifespan)

class MessageRequest(BaseModel):
    text:str
    # user_id: str | None = None
    # session_id: str | None = None
    # organization_id: str | None = None

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
    WorkflowState.FINAL_CONFIRMATION, WorkflowState.VENDOR_EXPANSION,
    WorkflowState.QUOTE_REQUEST, WorkflowState.VENDOR_POLICY_EVALUATION,
}

@api.post("/message", response_model=AssistantResponse)
async def send_message(req:MessageRequest):
    global latest_response, tokens, agents_tools, clean_message
    text=req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    captured_lines:list[str]=[]
    original_print=builtins.print
    builtins.print = lambda *args, **kwargs: captured_lines.append(" ".join(str(a) for a in args))

    try:
        if context.state in ACTIVE_STATES:
            await handle_state_input(text, context, engine.runner)
        elif context.state == WorkflowState.FEASIBILITY_ASSESSMENT:
            handle_feasibility_assessment(context)
        elif context.state == WorkflowState.FINAL_DOCUMENT_DRAFT:
            handle_final_document_draft(context)
        elif context.state == WorkflowState.COMPLETE:
            handle_complete(text, context)
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
        state=context.state.value,
        tokens=tokens,
        agents_tools=agents_tools,
        message=clean_message,
    )
@api.get("/response",response_model=AssistantResponse)
async def get_response():
    return AssistantResponse(state=context.state.value,tokens=tokens,agents_tools=agents_tools,message=clean_message)

@api.get("/state")
async def get_state():
    return {"state":context.state.value}



