import imagehash
from PIL import Image
import json
import os

HASH_HISTORY_PATH = "data/hash_history.json"
SIMILARITY_THRESHOLD = 5  # 해밍 거리 이 값 이하면 SIMILAR로 판단


def _compute_hash(image_path: str):
    img = Image.open(image_path)
    return imagehash.phash(img)


def _load_history() -> dict:
    if not os.path.exists(HASH_HISTORY_PATH):
        return {}
    with open(HASH_HISTORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_history(history: dict):
    os.makedirs(os.path.dirname(HASH_HISTORY_PATH), exist_ok=True)
    with open(HASH_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def check_duplicates(image_paths: list[str]) -> dict:
    """
    이미지 경로 리스트를 받아서 각 이미지의 중복 여부를 판단한다.
    - 같은 배치 내 다른 이미지와 비교
    - 과거에 저장된 해시 기록(다른 제출)과도 비교

    반환값 예:
    {
        "tctest08.jpg": {
            "duplicate_status": "SIMILAR",
            "matched_with": "tctest10.jpg",
            "distance": 3
        },
        ...
    }
    """
    history = _load_history()
    results = {}

    current_hashes = {}
    for path in image_paths:
        filename = os.path.basename(path)
        try:
            current_hashes[filename] = _compute_hash(path)
        except Exception:
            results[filename] = {
                "duplicate_status": "UNCERTAIN",
                "matched_with": None,
                "distance": None
            }

    for filename, h in current_hashes.items():
        best_match = None
        best_distance = None

        # 같은 배치 내 다른 이미지와 비교
        for other_filename, other_hash in current_hashes.items():
            if other_filename == filename:
                continue
            distance = h - other_hash
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_match = other_filename

        # 과거 기록과 비교 (다른 날/다른 학생 제출 포함)
        for past_filename, past_hash_str in history.items():
            past_hash = imagehash.hex_to_hash(past_hash_str)
            distance = h - past_hash
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_match = past_filename

        if best_distance is None:
            status = "UNIQUE"
        elif best_distance == 0:
            status = "EXACT_DUPLICATE"
        elif best_distance <= SIMILARITY_THRESHOLD:
            status = "SIMILAR"
        else:
            status = "UNIQUE"

        results[filename] = {
            "duplicate_status": status,
            "matched_with": best_match if status != "UNIQUE" else None,
            "distance": int(best_distance) if best_distance is not None else None
        }

    # 이번 배치 해시를 기록에 추가 저장 (다음 제출과 비교할 수 있도록)
    for filename, h in current_hashes.items():
        history[filename] = str(h)
    _save_history(history)

    return results