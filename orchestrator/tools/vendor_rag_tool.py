from google.adk.tools import FunctionTool
from services.vendor_rag_services import VendorRagService
from services.vendor_file_store import VendorRagFileSync

rag_service = VendorRagService()

if __name__ == "__main__":
    print("Rag Files : RAG FILES BEFORE UPLOAD",rag_service.list_files())

def _list_rag_files():
    """
    List all files currently stored
    in the procurement RAG corpus.
    """

    return VendorRagService.make_serializable(
        rag_service.list_files()
    )


def _upload_rag_file(
    gcs_uri: str
):
    """
    Add a new document to the
    procurement RAG corpus.

    Example:
    gs://my-bucket/vendor_policy.pdf
    """

    return rag_service.upload_file(
        gcs_uri=gcs_uri
    )

def _get_rag_file(
    file_name: str
):
    """
    Get metadata for a specific
    RAG file.
    """

    return VendorRagService.make_serializable(
        rag_service.get_file(
            file_name=file_name
        )
    )


def _delete_rag_file(
    file_name: str
):
    """
    Delete a file from the corpus.
    """

    return rag_service.delete_file(
        file_name=file_name
    )


def _replace_rag_file(
    old_file_name: str,
    new_gcs_uri: str
):
    """
    Replace an existing corpus file
    with a new document.
    """

    return rag_service.replace_file(
        old_file_name=old_file_name,
        new_gcs_uri=new_gcs_uri
    )

def _vendor_rag_search(
    query: str
) -> str:
    """
    Search the procurement knowledge base for
    vendor policies, approved vendors, contracts,
    pricing information and procurement documents.
    """

    return rag_service.query_text(
        question=query
    )

sync_service = VendorRagFileSync()


def _sync_vendors_tool(
    search_results: list[dict],
    corpus_state: dict | None = None,
):
    sync_result = sync_service.sync_vendors(
        search_results=search_results,
        corpus_state=corpus_state,
    )

    local_paths_to_import = list(sync_result.get("changed_files", []))

    current_corpus_files = rag_service.list_files()

    if len(current_corpus_files) == 0:
        local_paths_to_import = list({
            item["file_path"]
            for group_name in ("created", "updated", "unchanged")
            for item in sync_result.get(group_name, [])
            if item.get("status") == "active" and item.get("file_path")
        })

    imported_files = []

    for local_path in local_paths_to_import:
        import_result = rag_service.upload_local_file(local_path)

        imported_files.append({
            "local_path": local_path,
            "result": import_result,
        })

    return {
        **sync_result,
        "files_requested_for_import": local_paths_to_import,
        "imported_files": imported_files,
    }


vendor_rag_tool = FunctionTool(
    func=_vendor_rag_search
)

list_rag_files_tool = FunctionTool(
    func=_list_rag_files
)

get_rag_file_tool = FunctionTool(
    func=_get_rag_file
)

delete_rag_file_tool = FunctionTool(
    func=_delete_rag_file
)

replace_rag_file_tool = FunctionTool(
    func=_replace_rag_file
)

upload_rag_file_tool = FunctionTool(
    func=_upload_rag_file
)

sync_vendors_tool = FunctionTool(
    func=_sync_vendors_tool
)