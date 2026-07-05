from google.adk.tools import FunctionTool
from google.adk.tools import ToolContext

from orchestrator.core.workflow_state import (
    WorkflowState,
)

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
    WorkflowState.QUOTE_REQUEST, WorkflowState.VENDOR_POLICY_EVALUATION,
    
}

from orchestrator.core.procurement_context import ProcurementContext

from orchestrator.agents.handler import (
    handle_state_input,
    
)

async def workflow_dispatcher(
    text: str,
    tool_context: ToolContext,
):
    state = tool_context.state

    context = state.get("procurement_context")

    if context is None:
        context = ProcurementContext()
        state["procurement_context"] = context

    runner = tool_context.runner

    if context.state in ACTIVE_STATES:

        await handle_state_input(
            text,
            context,
            runner,
        )

    
    return {
        "state": context.state.value
    }

async def procurement_workflow_tool(
    user_message: str,
    tool_context: ToolContext,
):
    return await workflow_dispatcher(
        user_message,
        tool_context,
    )

procurement_workflow_tool = FunctionTool(
    func=procurement_workflow_tool,
)