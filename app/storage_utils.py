import logging
import mimetypes
import os
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger(__name__)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    or os.environ.get("SUPABASE_KEY", "").strip()
)
STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "homework-files").strip()

_client: Optional[Client] = None
_client_initialized = False


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _get_client() -> Optional[Client]:
    global _client, _client_initialized
    if _client_initialized:
        return _client

    _client_initialized = True
    if not is_configured():
        return None

    try:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        logger.exception("Supabase client initialization failed")
        _client = None
    return _client


def upload_file(file_path: str, object_path: str) -> None:
    client = _get_client()
    if client is None:
        raise RuntimeError("Supabase is not configured")

    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    with open(file_path, "rb") as file:
        client.storage.from_(STORAGE_BUCKET).upload(
            object_path,
            file,
            {"content-type": content_type, "upsert": "false"},
        )


def upload_submission_files(submission_id: str, file_paths: list[str]) -> dict:
    """Upload originals and return paths plus non-sensitive failure details."""
    uploaded_paths = []
    failures = []

    for file_path in file_paths:
        filename = os.path.basename(file_path)
        object_path = f"uploads/{submission_id}/{filename}"
        try:
            upload_file(file_path, object_path)
            uploaded_paths.append(object_path)
        except Exception as error:
            logger.exception("Supabase Storage upload failed for %s", filename)
            failures.append({"filename": filename, "error": str(error)})

    return {"paths": uploaded_paths, "failures": failures}


def persist_submission(record: dict, source_paths: Optional[list[str]] = None) -> dict:
    """Persist a submission remotely without making remote failure fatal."""
    client = _get_client()
    if client is None:
        return {"enabled": False, "storage_failures": [], "db_error": None}

    upload_result = upload_submission_files(record["submission_id"], source_paths or [])
    storage_error = None
    if upload_result["failures"]:
        storage_error = "One or more source files could not be uploaded."

    payload = dict(record)
    payload["storage_paths"] = upload_result["paths"]
    payload["storage_error"] = storage_error

    db_error = None
    try:
        client.table("submissions").insert(payload).execute()
    except Exception as error:
        logger.exception("Supabase submission insert failed for %s", record["submission_id"])
        db_error = str(error)

    return {
        "enabled": True,
        "storage_failures": upload_result["failures"],
        "db_error": db_error,
    }


def fetch_submissions() -> Optional[list[dict]]:
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.table("submissions").select(
            "submission_id,student_name,student_id,subject,assignment_name,"
            "submitted_at,processing_status,error,results"
        ).order("submitted_at", desc=False).execute()
        return response.data or []
    except Exception:
        logger.exception("Supabase submissions query failed")
        return None


def save_duplicate_history(entries: dict) -> bool:
    client = _get_client()
    if client is None or not entries:
        return False

    rows = [
        {"history_key": history_key, "hash_value": hash_value}
        for history_key, hash_value in entries.items()
    ]
    try:
        client.table("duplicate_history").upsert(rows, on_conflict="history_key").execute()
        return True
    except Exception:
        logger.exception("Supabase duplicate history save failed")
        return False


def fetch_duplicate_history() -> Optional[dict]:
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.table("duplicate_history").select("history_key,hash_value").execute()
        return {
            row["history_key"]: row["hash_value"]
            for row in (response.data or [])
            if row.get("history_key") and row.get("hash_value")
        }
    except Exception:
        logger.exception("Supabase duplicate history query failed")
        return None
