from vertexai.preview import rag
import os
from pathlib import Path
from google.cloud import storage
from dotenv import load_dotenv
import base64
import json
from google.oauth2 import service_account

load_dotenv()


class VendorRagService:
    def _get_credentials(self):
        service_account_base64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_BASE64")
        if not service_account_base64:
            return None

        service_account_info = json.loads(
            base64.b64decode(service_account_base64).decode("utf-8")
        )

        return service_account.Credentials.from_service_account_info(
            service_account_info
        )

    def _get_corpus_name(self) -> str:
        corpus_name = os.getenv(
            "VERTEX_RAG_CORPUS_NAME"
        )

        if not corpus_name:
            raise ValueError(
                "VERTEX_RAG_CORPUS_NAME is not configured"
            )

        return corpus_name

    @staticmethod
    def _serialize_rag_file(rag_file) -> dict:
        create_time = getattr(rag_file, "create_time", None)
        update_time = getattr(rag_file, "update_time", None)

        return {
            "name": getattr(rag_file, "name", None),
            "display_name": getattr(rag_file, "display_name", None),
            "description": getattr(rag_file, "description", None),
            "create_time": str(create_time) if create_time else None,
            "update_time": str(update_time) if update_time else None,
        }


    @staticmethod
    def make_serializable(obj):
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj

        if isinstance(obj, dict):
            return {
                key: VendorRagService.make_serializable(value)
                for key, value in obj.items()
            }

        if isinstance(obj, (list, tuple)):
            return [
                VendorRagService.make_serializable(item)
                for item in obj
            ]

        if hasattr(obj, "name") and hasattr(obj, "display_name"):
            return VendorRagService._serialize_rag_file(obj)

        return str(obj)

    # ---------- Upload ----------
    def _serialize_import_response(
        self,
        response,
        gcs_uris: list[str],
    ) -> dict:
        return {
            "status": "import_completed",
            "gcs_uris": gcs_uris,
            "imported_rag_files_count": int(
                getattr(response, "imported_rag_files_count", 0) or 0
            ),
            "failed_rag_files_count": int(
                getattr(response, "failed_rag_files_count", 0) or 0
            ),
            "skipped_rag_files_count": int(
                getattr(response, "skipped_rag_files_count", 0) or 0
            ),
            "partial_failures_gcs_path": (
                getattr(response, "partial_failures_gcs_path", "") or None
            ),
            "partial_failures_bigquery_table": (
                getattr(response, "partial_failures_bigquery_table", "") or None
            ),
        }

    def upload_file(
        self,
        gcs_uri: str
    ):
        response = rag.import_files(
            self._get_corpus_name(),
            paths=[gcs_uri]
        )

        return self._serialize_import_response(
            response=response,
            gcs_uris=[gcs_uri],
        )

    def upload_files(
        self,
        gcs_uris: list[str]
    ):
        response = rag.import_files(
            self._get_corpus_name(),
            paths=gcs_uris
        )

        return self._serialize_import_response(
            response=response,
            gcs_uris=gcs_uris,
        )

    def upload_local_file(
        self,
        local_path: str,
    ):
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME is not configured")

        path = Path(local_path)
        blob_name = f"rag_vendor_files/{path.name}"

        client = storage.Client(
            project=os.getenv("VERTEX_AI_RAG_PROJECT_ID"),
            credentials=self._get_credentials(),
        )
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        blob.upload_from_filename(str(path))

        gcs_uri = f"gs://{bucket_name}/{blob_name}"

        return self.upload_file(gcs_uri)

    # ---------- File Management ----------

    def list_files(self):
        raw_files = list(
            rag.list_files(
                corpus_name=self._get_corpus_name()
            )
        )

        return [
            self._serialize_rag_file(rag_file)
            for rag_file in raw_files
        ]

    def get_file(
        self,
        file_name: str
    ):
        return self._serialize_rag_file(
            rag.get_file(
                name=file_name
            )
        )

    def delete_file(
        self,
        file_name: str
    ):

        rag.delete_file(
            name=file_name
        )

        return f"Deleted {file_name}"

    def replace_file(
        self,
        old_file_name: str,
        new_gcs_uri: str
    ):

        rag.delete_file(
            name=old_file_name
        )

        response = rag.import_files(
            self._get_corpus_name(),
            paths=[new_gcs_uri]
        )

        return self._serialize_import_response(
            response=response,
            gcs_uris=[new_gcs_uri],
        )

    # ---------- Query ----------

    def query(
        self,
        question: str,
        top_k: int = 4
    ):

        return rag.retrieval_query(
            rag_resources=[
                rag.RagResource(
                    rag_corpus=self._get_corpus_name()
                )
            ],
            text=question,
            similarity_top_k=top_k,
        )

    def query_text(
        self,
        question: str,
        top_k: int = 4,
        max_chars_per_chunk: int = 900,
        max_total_chars: int = 3500,
    ) -> str:
        response = self.query(
            question=question,
            top_k=top_k
        )

        chunks = []
        seen = set()

        for chunk in response.contexts.contexts:
            text = " ".join((chunk.text or "").split())
            if not text:
                continue

            key = text[:300]
            if key in seen:
                continue
            seen.add(key)

            chunks.append(text[:max_chars_per_chunk])

            if sum(len(item) for item in chunks) >= max_total_chars:
                break

        return "\n\n".join(chunks)[:max_total_chars]