from PIL import Image
from app.storage_utils import fetch_duplicate_history, save_duplicate_history
import json
import os
import time
import uuid

DATA_DIR = os.environ.get("DATA_DIR", "data")
HASH_HISTORY_PATH = os.path.join(DATA_DIR, "hash_history.json")
SIMILARITY_THRESHOLD = 5
HASH_PREFIX = "dhash:"
HASH_SIZE = 8


def _compute_hash(image_path: str) -> int:
    """Compute a small perceptual dHash without NumPy or SciPy."""
    hash_started = time.perf_counter()
    print(f"[PERF] dHash START path={os.path.basename(image_path)}", flush=True)
    with Image.open(image_path) as source:
        source.draft("L", (HASH_SIZE + 1, HASH_SIZE))
        image = source.convert("L")
        image.thumbnail((HASH_SIZE + 1, HASH_SIZE), Image.Resampling.LANCZOS)
        image = image.resize((HASH_SIZE + 1, HASH_SIZE), Image.Resampling.LANCZOS)
        pixels = list(image.getdata())

    value = 0
    for row in range(HASH_SIZE):
        offset = row * (HASH_SIZE + 1)
        for column in range(HASH_SIZE):
            value <<= 1
            if pixels[offset + column] > pixels[offset + column + 1]:
                value |= 1
    print(f"[PERF] dHash END path={os.path.basename(image_path)} elapsed={time.perf_counter() - hash_started:.2f}s", flush=True)
    return value


def _load_history() -> dict:
    local_history = {}
    if not os.path.exists(HASH_HISTORY_PATH):
        local_history = {}
    else:
        try:
            with open(HASH_HISTORY_PATH, "r", encoding="utf-8") as file:
                local_history = json.load(file)
        except (json.JSONDecodeError, OSError):
            local_history = {}

    remote_history = fetch_duplicate_history()
    if remote_history is not None:
        local_history.update(remote_history)
    return local_history


def _save_history(history: dict) -> None:
    os.makedirs(os.path.dirname(HASH_HISTORY_PATH), exist_ok=True)
    with open(HASH_HISTORY_PATH, "w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)
    save_duplicate_history(history)


def _distance(first: int, second: int) -> int:
    return (first ^ second).bit_count()


def check_duplicates(image_paths: list[str]) -> dict:
    """Check similar images without loading SciPy or ImageHash."""
    duplicates_started = time.perf_counter()
    print("[PERF] check_duplicates START", flush=True)
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
                "distance": None,
            }

    for filename, image_hash in current_hashes.items():
        best_match = None
        best_distance = None

        for other_filename, other_hash in current_hashes.items():
            if other_filename == filename:
                continue
            distance = _distance(image_hash, other_hash)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_match = other_filename

        for past_filename, past_hash_text in history.items():
            if not isinstance(past_hash_text, str) or not past_hash_text.startswith(HASH_PREFIX):
                continue
            try:
                past_hash = int(past_hash_text[len(HASH_PREFIX):], 16)
            except ValueError:
                continue
            distance = _distance(image_hash, past_hash)
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
            "distance": best_distance if best_distance is not None else None,
        }

    for filename, image_hash in current_hashes.items():
        history[f"{filename}#{uuid.uuid4().hex}"] = f"{HASH_PREFIX}{image_hash:016x}"
    _save_history(history)

    print(f"[PERF] check_duplicates END elapsed={time.perf_counter() - duplicates_started:.2f}s", flush=True)
    return results
