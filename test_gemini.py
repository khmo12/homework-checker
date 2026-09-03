from dotenv import load_dotenv
from google import genai
import os
import json
import glob

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# data 폴더 안의 이미지 파일들을 순서대로 불러오기
image_paths = sorted(glob.glob("data/*.jpg"))

if not image_paths:
    print("data 폴더에 이미지가 없습니다.")
    exit()

print(f"총 {len(image_paths)}장의 이미지를 처리합니다: {image_paths}")

# 각 이미지를 업로드하고, image_index를 붙여서 순서를 관리
uploaded_files = []
for idx, path in enumerate(image_paths):
    uploaded = client.files.upload(file=path)
    uploaded_files.append({
        "index": idx,
        "filename": os.path.basename(path),
        "file_obj": uploaded
    })
    print(f"업로드 완료 [{idx}]: {path}")

system_prompt = f"""
너는 학교 숙제 검사 보조 AI다.

너의 역할은 숙제를 채점하는 것이 아니라,
"이 학생이 숙제를 실제로 수행했는가?"를 1차로 판단하는 것이다.

판정 기준:
- PASS: 사진만 봤을 때 학생이 숙제를 실제로 수행했다고 합리적으로 볼 수 있음.
  (조금 부족해도 실제로 했다면 PASS)
- FAIL: 거의 하지 않았거나 사실상 백지 수준.
- REVIEW: 사진 품질(흐림/가림/과도한 접사/잘림/어두움 등) 때문에
  숙제 수행 여부 자체를 판단할 수 없는 경우.

정답률, 글씨체, 오답노트의 형식적 완성도를 과도하게 평가하지 않는다.
오답 정리가 없어도 문제풀이 흔적이 충분하면 PASS 가능하다.
페이지 전체 맥락(전체 페이지가 보이는지)을 반드시 고려한다.

이번 숙제는 "국어" 과목이다.
만약 이미지가 국어 숙제가 아니라 다른 과목(예: 수학, 영어 등)의 숙제로 보인다면,
assignment_match를 "mismatch"로 표시하고 result는 FAIL로 판정하라.
(다른 과목 숙제를 열심히 했다는 이유로 PASS하면 안 된다.)

지금부터 총 {len(uploaded_files)}장의 이미지가 순서대로 주어진다.
각 이미지는 image_index 0부터 {len(uploaded_files)-1}까지 순서대로 대응한다.

반드시 아래 JSON 배열 형식으로만 응답하라. 이미지 개수만큼 배열 원소를 만들어라.
다른 설명이나 텍스트는 절대 추가하지 마라.

[
  {{
    "image_index": 0,
    "result": "PASS 또는 FAIL 또는 REVIEW",
    "confidence": "high 또는 medium 또는 low",
    "page_type": "problem_only 또는 passage_only 또는 passage_and_problem 또는 unknown",
    "photo_quality": {{
      "full_page_visible": true 또는 false,
      "readability": "good 또는 fair 또는 poor",
      "obstruction": true 또는 false
    }},
    "assignment_match": {{
      "status": "match 또는 mismatch",
      "reason": "간단한 이유"
    }},
    "work_evidence": {{
      "problem_solving": true 또는 false,
      "grading_marks": true 또는 false,
      "correction_or_review": true 또는 false,
      "summary": true 또는 false,
      "structure_map": true 또는 false
    }},
    "reason": "판정 이유를 한국어로 1~2문장",
    "missing_or_weak": ["부족했던 부분들을 간단히 나열, 없으면 빈 배열"]
  }}
]
"""

# contents 구성: 프롬프트 + 이미지들 (순서대로)
contents = [system_prompt]
for item in uploaded_files:
    contents.append(item["file_obj"])

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=contents,
    config={
        "response_mime_type": "application/json"
    }
)

result_json = json.loads(response.text)

# image_index를 실제 파일명과 매칭해서 보기 좋게 출력
print("\n=== 판정 결과 ===")
for entry in result_json:
    idx = entry.get("image_index")
    filename = uploaded_files[idx]["filename"] if idx is not None and idx < len(uploaded_files) else "알 수 없음"
    entry["matched_filename"] = filename

print(json.dumps(result_json, ensure_ascii=False, indent=2))