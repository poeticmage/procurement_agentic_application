from google.adk.tools import FunctionTool

from services.container import corpus_manager


def _vendor_rag_search(
    org_id: str,
    query: str,
    top_k: int = 10
) -> str:
    """
    Search procurement knowledge stored in the
    organization's Vertex AI RAG corpus.
    """

    return corpus_manager.query_org(
        org_id=org_id,
        question=query
    )


vendor_rag_tool = FunctionTool(
    _vendor_rag_search
)