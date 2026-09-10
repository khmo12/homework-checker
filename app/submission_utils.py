import json
import os
import uuid
from datetime import datetime
from app.storage_utils import fetch_submissions, persist_submission

DATA_DIR = os.environ.get("DATA_DIR", "data")
SUBMISSIONS_FILE = os.path.join(DATA_DIR, "submissions.json")


def _load_all():
    if not os.path.exists(SUBMISSIONS_FILE):
        return []
    with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_all(submissions):
    os.makedirs(os.path.dirname(SUBMISSIONS_FILE), exist_ok=True)
    with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(submissions, f, ensure_ascii=False, indent=2)


def save_submission(student_name, subject_name, assignment_name, check_result, student_id="", source_paths=None):
    submissions = _load_all()
    record = {
        "submission_id": str(uuid.uuid4()),
        "student_name": student_name,
        "student_id": student_id,
        "subject": subject_name,
        "assignment_name": assignment_name,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "processing_status": check_result.get("processing_status"),
        "error": check_result.get("error"),
        "results": check_result.get("results", []),
    }
    submissions.append(record)
    _save_all(submissions)
    persist_submission(record, source_paths=source_paths)
    return record


def get_all_submissions():
    local_submissions = _load_all()
    remote_submissions = fetch_submissions()
    if remote_submissions is None:
        return local_submissions

    submissions_by_id = {submission["submission_id"]: submission for submission in local_submissions}
    submissions_by_id.update(
        {submission["submission_id"]: submission for submission in remote_submissions}
    )
    return list(submissions_by_id.values())


def get_submissions_by_student(student_name):
    return [s for s in get_all_submissions() if s["student_name"] == student_name]