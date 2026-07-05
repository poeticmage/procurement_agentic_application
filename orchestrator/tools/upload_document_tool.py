from google.adk.tools import FunctionTool
from vertexai.preview import rag
from services.vendor_rag_services import VendorRagService
import os

#  THIS IS CUSTOM RAG TOOL IN CASE YOU WANT TO USE IT, OTHERWISE VERTEX AI DIRECTLY PROVIDES SERVICE FOR IT
def upload_document_tool(
    gcs_uri: str
):
    """
    Upload a document into the configured Vertex AI RAG corpus.

    Example:
    gs://adkbucket_123/contracts/vendor1.pdf
    """

    corpus_name = os.getenv(
        "VERTEX_RAG_CORPUS_NAME"
    )

    if not corpus_name:
        raise ValueError(
            "VERTEX_RAG_CORPUS_NAME is not configured"
        )

    return VendorRagService().upload_file(
    gcs_uri=gcs_uri
)

upload_document_tool = FunctionTool(
    func=upload_document_tool
)