from datetime import datetime, timezone

import orchestrator.agents.handler as _handler  # import the module, not the name

from orchestrator.agents.handler import (
    extract_document_facts,
    merge_document_facts,
    build_procurement_document,
)

from orchestrator.core.workflow_state import WorkflowState
from orchestrator.tools.procurement_document_tool import write_procurement_pdf
from google.adk.tools import FunctionTool


def generate_procurement_document_tool():
    """
    Generate procurement PDF from the active workflow context.

    Intended to be called by vendor_agent after vendor selection.

    This tool:
    - Extracts latest document facts
    - Builds ProcurementDocument
    - Generates PDF
    - Uploads PDF (handled by write_procurement_pdf)
    - Returns download URL

    This tool does NOT:
    - Change workflow state
    - Perform HIL approval
    - Start negotiation
    """

    context = _handler._ACTIVE_PROCUREMENT_CONTEXT  # read live value through module reference

    if context is None:
        return {
            "status": "error",
            "message": "No active procurement context found."
        }

    try:
        extracted_facts = extract_document_facts(
            current_state=WorkflowState.FINAL_DOCUMENT_DRAFT,
            latest_user_message="",
            context=context,
        )

        merge_document_facts(
            context,
            extracted_facts,
        )

        document = build_procurement_document(
            context,
            final_summary=f"Vendor locked: {context.selected_vendor}",
        )

        result = write_procurement_pdf(
            document.model_dump(mode="json")
        )

        hil = context.metadata.setdefault("hil", {})
        if hil.get("status") == "pending" and context.document_path:
            existing = context.metadata.get("document_result") or {}
            return {
                "status": "already_generated",
                "document_id": existing.get("document_id"),
                "document_path": context.document_path,
                "download_url": context.document_download_url,
                "message": "Document already generated. Awaiting user approval.",
            }

        context.document = document
        context.document_path = result.get("document_path")
        context.document_download_url = result.get("download_url")

        context.metadata["document_result"] = {
            "status": result.get("status"),
            "document_id": result.get("document_id"),
            "document_path": result.get("document_path"),
            "download_url": result.get("download_url"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        context.metadata["hil_review_payload"] = {
            "document_id": result.get("document_id"),
            "document_path": result.get("document_path"),
            "download_url": result.get("download_url"),
            "document": document.model_dump(mode="json"),
        }
        hil.update({
            "status": "pending",
            "review_started_at": datetime.now(timezone.utc).isoformat(),
            "review_decision": None,
            "reviewer_input": None,
            "approved": False,
            "rejection_reason": None,
        })

        return {
            "status": result.get("status"),
            "document_id": result.get("document_id"),
            "document_path": result.get("document_path"),
            "download_url": result.get("download_url"),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }


generate_document_tool = FunctionTool(
    func=generate_procurement_document_tool
)