import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class VendorFileStore:
    def __init__(self, base_dir: str = "rag_vendor_files"):
        self.base_dir = Path(base_dir)
        self.index_path = self.base_dir / "_vendor_index.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_vendor_file(self, vendor: dict[str, Any]) -> dict[str, Any]:
        vendor_key = self._vendor_key(vendor)
        index = self._load_index()

        if vendor_key in index:
            return self.update_vendor_file(vendor)

        record = {
            "vendor_key": vendor_key,
            "status": "active",
            "version": 1,
            "updated_at": self._now(),
            "vendor": vendor,
        }

        return self._write_vendor_record(record)

    def update_vendor_file(self, vendor: dict[str, Any]) -> dict[str, Any]:
        vendor_key = self._vendor_key(vendor)
        existing_record = self._read_vendor_record(vendor_key)

        if not existing_record:
            return self.create_vendor_file(vendor)

        merged_vendor = self._merge_vendor_data(
            existing=existing_record.get("vendor", {}),
            incoming=vendor,
        )

        record = {
            "vendor_key": vendor_key,
            "status": "active",
            "version": int(existing_record.get("version", 1)) + 1,
            "updated_at": self._now(),
            "vendor": merged_vendor,
        }

        old_content = self._render_vendor_record(existing_record)
        new_content = self._render_vendor_record(record)

        if self._hash(old_content) == self._hash(new_content):
            return self._load_index()[vendor_key]

        return self._write_vendor_record(record)

    def delete_vendor_file(self, vendor: dict[str, Any] | str) -> dict[str, Any]:
        vendor_key = vendor if isinstance(vendor, str) else self._vendor_key(vendor)
        existing_record = self._read_vendor_record(vendor_key)

        if not existing_record:
            return {
                "vendor_key": vendor_key,
                "status": "missing",
                "changed": False,
            }

        record = {
            **existing_record,
            "status": "deprecated",
            "version": int(existing_record.get("version", 1)) + 1,
            "updated_at": self._now(),
        }

        return self._write_vendor_record(record)

    def sync_vendors(
        self,
        search_results: list[dict[str, Any]],
        corpus_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        index = self._load_index()
        incoming_by_key = self._dedupe_search_results(search_results)

        created = []
        updated = []
        unchanged = []

        for vendor_key, incoming_vendor in incoming_by_key.items():
            if vendor_key not in index:
                created.append(self.create_vendor_file(incoming_vendor))
                continue

            before = index[vendor_key]
            after = self.update_vendor_file(incoming_vendor)

            if before.get("content_hash") == after.get("content_hash"):
                unchanged.append(after)
            else:
                updated.append(after)

        return {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "changed_files": [
                item["file_path"]
                for item in created + updated
            ],
        }

    def _dedupe_search_results(
        self,
        search_results: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        vendors: dict[str, dict[str, Any]] = {}

        for vendor in search_results:
            vendor_key = self._vendor_key(vendor)

            if vendor_key not in vendors:
                vendors[vendor_key] = vendor
            else:
                vendors[vendor_key] = self._merge_vendor_data(
                    existing=vendors[vendor_key],
                    incoming=vendor,
                )

        return vendors

    def _write_vendor_record(self, record: dict[str, Any]) -> dict[str, Any]:
        vendor_key = record["vendor_key"]
        file_path = self.base_dir / f"{vendor_key}.txt"
        content = self._render_vendor_record(record)
        content_hash = self._hash(content)

        file_path.write_text(content, encoding="utf-8")

        index = self._load_index()
        index[vendor_key] = {
            "vendor_key": vendor_key,
            "file_path": str(file_path),
            "status": record["status"],
            "version": record["version"],
            "content_hash": content_hash,
            "updated_at": record["updated_at"],
        }
        self._save_index(index)

        return index[vendor_key]

    def _read_vendor_record(self, vendor_key: str) -> dict[str, Any] | None:
        index = self._load_index()
        entry = index.get(vendor_key)

        if not entry:
            return None

        file_path = Path(entry["file_path"])

        if not file_path.exists():
            return None

        text = file_path.read_text(encoding="utf-8")
        marker = "RAW_VENDOR_JSON:"

        if marker not in text:
            return None

        try:
            return json.loads(text.split(marker, 1)[1].strip())
        except json.JSONDecodeError:
            return None

    def _merge_vendor_data(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(existing)

        for key, incoming_value in incoming.items():
            if incoming_value in (None, "", [], {}):
                continue

            existing_value = merged.get(key)

            if existing_value in (None, "", [], {}):
                merged[key] = incoming_value
                continue

            if isinstance(existing_value, list) and isinstance(incoming_value, list):
                merged[key] = list(dict.fromkeys(existing_value + incoming_value))
                continue

            if isinstance(existing_value, dict) and isinstance(incoming_value, dict):
                merged[key] = {
                    **existing_value,
                    **{
                        nested_key: nested_value
                        for nested_key, nested_value in incoming_value.items()
                        if nested_value not in (None, "", [], {})
                    },
                }
                continue

            if existing_value != incoming_value:
                merged[key] = incoming_value

        return merged

    def _render_vendor_record(self, record: dict[str, Any]) -> str:
        vendor = record.get("vendor", {})

        lines = [
            f"Vendor Name: {vendor.get('vendor_name') or vendor.get('name') or 'Unknown'}",
            f"Vendor Key: {record.get('vendor_key')}",
            f"Status: {record.get('status')}",
            f"Version: {record.get('version')}",
            f"Updated At: {record.get('updated_at')}",
            f"Website: {vendor.get('website') or vendor.get('url') or 'unknown'}",
            f"Approval Status: {vendor.get('approval_status', 'unknown')}",
            f"Risk Level: {vendor.get('risk_level', 'unknown')}",
            f"Capabilities: {', '.join(vendor.get('capabilities', []))}",
            f"Policy Notes: {'; '.join(vendor.get('policy_notes', []))}",
            f"Source URLs: {', '.join(vendor.get('source_urls', []))}",
            f"Evidence Summary: {vendor.get('evidence_summary', '')}",
            "",
            "RAW_VENDOR_JSON:",
            json.dumps(record, indent=2, sort_keys=True),
            "",
        ]

        return "\n".join(lines)

    def _vendor_key(self, vendor: dict[str, Any]) -> str:
        identity = (
            vendor.get("vendor_id")
            or vendor.get("vendor_name")
            or vendor.get("name")
            or vendor.get("title")
            or self._domain_from_url(vendor.get("website") or vendor.get("url") or "")
            or ""
        )

        identity = str(identity).strip().lower()

        if not identity:
            identity = json.dumps(vendor, sort_keys=True)

        slug = re.sub(r"^https?://", "", identity)
        slug = re.sub(r"^www\.", "", slug)
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")

        if not slug:
            slug = "unknown-vendor"

        digest = hashlib.sha256(
            json.dumps(vendor, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]

        max_slug_length = 80
        safe_slug = slug[:max_slug_length].strip("-")

        return f"{safe_slug}-{digest}"

    def _domain_from_url(self, value: str) -> str:
        value = str(value or "").strip().lower()

        if not value:
            return ""

        value = re.sub(r"^https?://", "", value)
        value = re.sub(r"^www\.", "", value)

        return value.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {}

        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_index(self, index: dict[str, Any]) -> None:
        self.index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class VendorRagFileSync:
    def __init__(self, file_store: VendorFileStore | None = None):
        self.file_store = file_store or VendorFileStore()
    def sync_vendors(
        self,
        search_results: list[dict[str, Any]],
        corpus_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.file_store.sync_vendors(
            search_results=search_results,
            corpus_state=corpus_state,
        )