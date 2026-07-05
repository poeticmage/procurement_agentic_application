from __future__ import annotations

import logging
import time
from typing import Any

from a2a.server.agent_execution.context import RequestContext
from a2a.types import TaskStatusUpdateEvent
from google.adk.a2a.converters.part_converter import (
    convert_a2a_part_to_genai_part,
)
from google.adk.a2a.converters.request_converter import (
    AgentRunRequest,
    convert_a2a_request_to_agent_run_request,
)
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig, ExecuteInterceptor
from google.adk.runners import RunConfig

logger = logging.getLogger(__name__)

_REQUEST_START_TIMES: dict[str, float] = {}
REQUIRED_METADATA_FIELDS = ("user_id", "org_id", "user_name", "org_name")


def _query_preview(request: RequestContext) -> str:
    message = getattr(request, "message", None)
    if not message:
        return ""

    parts = getattr(message, "parts", None) or []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            preview = str(text).strip().replace("\n", " ")
            return preview[:120] + ("..." if len(preview) > 120 else "")

    return ""


async def _record_start_time(context: RequestContext) -> RequestContext:
    task_id = getattr(context, "task_id", None)
    context_id = getattr(context, "context_id", None)

    if task_id:
        _REQUEST_START_TIMES[task_id] = time.perf_counter()

    logger.info(
        "a2a_request_start task_id=%s context_id=%s query_preview=%r",
        task_id,
        context_id,
        _query_preview(context),
    )
    return context


async def _attach_time_taken(executor_context, final_event: TaskStatusUpdateEvent):
    task_id = final_event.task_id
    started = _REQUEST_START_TIMES.pop(task_id, None)
    duration_sec = None

    if started is not None:
        duration_sec = round(time.perf_counter() - started, 2)
        metadata = dict(final_event.metadata or {})
        metadata["time_taken"] = duration_sec
        final_event.metadata = metadata

    status = getattr(getattr(final_event, "status", None), "state", None)
    logger.info(
        "a2a_request_end task_id=%s duration_sec=%s status=%s",
        task_id,
        duration_sec,
        status or "unknown",
    )
    return final_event


def stable_request_converter(
    request: RequestContext,
    part_converter=convert_a2a_part_to_genai_part,
) -> AgentRunRequest:
    context_id = getattr(request, "context_id", None)
    metadata: dict[str, Any] = getattr(request, "metadata", None) or {}

    logger.info(
        "a2a_request_convert context_id=%s metadata_keys=%s",
        context_id,
        sorted(metadata.keys()),
    )

    try:
        run_request = convert_a2a_request_to_agent_run_request(
            request,
            part_converter,
        )
    except Exception:
        logger.exception(
            "a2a_request_convert_failed step=base_conversion context_id=%s",
            context_id,
        )
        raise

    missing = [field for field in REQUIRED_METADATA_FIELDS if not metadata.get(field)]
    if missing:
        logger.error(
            "a2a_request_rejected step=metadata_validation context_id=%s "
            "missing_fields=%s",
            context_id,
            ",".join(missing),
        )
        raise ValueError(
            f"Missing required A2A metadata fields: {', '.join(missing)}"
        )

    user_id = str(metadata["user_id"])
    org_id = str(metadata["org_id"])
    user_name = str(metadata["user_name"])
    org_name = str(metadata["org_name"])

    if not context_id:
        logger.error(
            "a2a_request_rejected step=context_validation reason=missing_context_id"
        )
        raise ValueError(
            "A2A context_id is required because it is used as ADK session_id"
        )

    run_request.user_id = user_id
    run_request.session_id = context_id

    run_request.state_delta = {
        **(run_request.state_delta or {}),
        "user:user_id": user_id,
        "user:org_id": org_id,
        "user:user_name": user_name,
        "user:org_name": org_name,
    }

    existing_custom_metadata = {}
    if run_request.run_config and run_request.run_config.custom_metadata:
        existing_custom_metadata.update(run_request.run_config.custom_metadata)

    existing_custom_metadata.update(
        {
            "user_id": user_id,
            "org_id": org_id,
            "user_name": user_name,
            "org_name": org_name,
        }
    )

    run_request.run_config = RunConfig(
        custom_metadata=existing_custom_metadata,
    )

    logger.info(
        "a2a_request_mapped context_id=%s user_id=%s org_id=%s",
        context_id,
        user_id,
        org_id,
    )

    return run_request


def make_agent_executor(runner_instance):
    logger.info("a2a_executor_factory_initialized")

    return A2aAgentExecutor(
        runner=runner_instance,
        config=A2aAgentExecutorConfig(
            request_converter=stable_request_converter,
            execute_interceptors=[
                ExecuteInterceptor(
                    before_agent=_record_start_time,
                    after_agent=_attach_time_taken,
                )
            ],
        ),
    )
