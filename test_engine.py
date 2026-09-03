from app.ai_engine import check_homework
import json

image_paths = [
    "data/tctest06.jpg",
    "data/tctest06.jpg",
    "data/tctest08.jpg",
    "data/tctest09.jpg",
    "data/tctest10.jpg",
]

result = check_homework(image_paths, subject_name="국어")

print(json.dumps(result, ensure_ascii=False, indent=2))