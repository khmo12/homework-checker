import json
import os
import uuid
from datetime import datetime

SUBMISSIONS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "submissions.json",
)


def _load_all():
    if not os.path.exists(SUBMISSIONS_FILE):
        return []
    with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_all(submissions):
    with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(submissions, f, ensure_ascii=False, indent=2)


def save_submission(student_name, subject_name, assignment_name, check_result):
    submissions = _load_all()
    record = {
        "submission_id": str(uuid.uuid4()),
        "student_name": student_name,
        "subject": subject_name,
        "assignment_name": assignment_name,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "processing_status": check_result.get("processing_status"),
        "error": check_result.get("error"),
        "results": check_result.get("results", []),
    }
    submissions.append(record)
    _save_all(submissions)
    return record


def get_all_submissions():
    return _load_all()


def get_submissions_by_student(student_name):
    return [s for s in _load_all() if s["student_name"] == student_name]