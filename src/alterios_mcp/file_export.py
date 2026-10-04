"""Bounded downloads to a private artifact directory; no caller-supplied URLs."""
from __future__ import annotations

import hashlib
import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .client import AlteriosConfigError, AlteriosRequestError, path_segment
from .write_plan import artifact_root


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward project credentials to a login page/CDN/foreign origin.
        raise AlteriosRequestError("File download redirect rejected; use the authenticated file-ID route")


def download_bounded(client, file_id: str, max_bytes: int) -> tuple[bytes, str]:
    if not file_id.strip() or len(file_id) > 256 or not 1 <= max_bytes <= 50 * 1024 * 1024:
        raise ValueError("Invalid file_id or byte limit")
    missing = client.config.missing_for_project_call()
    if missing:
        raise AlteriosConfigError("File download requires explicit configured project")
    request = Request(client.config.base_url.rstrip("/") + "/api/file/download/" + path_segment(file_id),
                      headers=client._headers(), method="GET")
    try:
        with build_opener(NoRedirect()).open(request, timeout=client.config.timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            if content_type.lower().startswith("text/html"):
                raise AlteriosRequestError("HTML response rejected; possibly a login page")
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > max_bytes:
                raise AlteriosRequestError("File exceeds byte limit")
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise AlteriosRequestError("File exceeds byte limit")
            if length is not None and len(data) != int(length):
                raise AlteriosRequestError("File download length mismatch")
            return data, content_type
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AlteriosRequestError("File download failed: " + type(exc).__name__) from exc


def export_files(client, file_ids: list[str], *, max_file_bytes: int = 10 * 1024 * 1024,
                 max_total_bytes: int = 50 * 1024 * 1024) -> dict:
    if not file_ids or len(file_ids) > 50 or len(file_ids) != len(set(file_ids)):
        raise ValueError("Select 1-50 distinct file IDs")
    if any(not isinstance(x, str) or not x.strip() or len(x) > 256 for x in file_ids):
        raise ValueError("Invalid file ID")
    if not 1 <= max_file_bytes <= 50 * 1024 * 1024 or not 1 <= max_total_bytes <= 200 * 1024 * 1024:
        raise ValueError("Invalid byte limits")
    directory = artifact_root() / "file-exports" / ("files_" + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    entries = []
    total = 0
    for index, file_id in enumerate(file_ids):
        try:
            if total >= max_total_bytes:
                raise AlteriosRequestError("Export total byte limit reached")
            data, content_type = download_bounded(client, file_id, min(max_file_bytes, max_total_bytes - total))
            # Never use a remote filename or arbitrary file ID as a local path.
            name = f"{index + 1:04d}.bin"
            path = directory / name
            with path.open("xb") as stream:
                stream.write(data)
            digest = hashlib.sha256(data).hexdigest()
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != digest:
                raise OSError("Stored file checksum mismatch")
            total += len(data)
            entries.append({"file_id": file_id, "filename": name, "content_type": content_type,
                            "bytes": len(data), "sha256": digest, "verified": True})
        except (AlteriosRequestError, OSError, ValueError) as exc:
            entries.append({"file_id": file_id, "verified": False, "error_type": type(exc).__name__,
                            "message": str(exc) if isinstance(exc, AlteriosRequestError) else "Local file verification failed"})
    result = {"readonly": True, "remote_write": False, "directory": str(directory),
              "target": {"profile": client.config.profile, "project_id": client.config.project_id},
              "complete": all(e["verified"] for e in entries), "bytes": total, "files": entries}
    (directory / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
