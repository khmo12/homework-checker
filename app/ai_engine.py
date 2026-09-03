from app.duplicate_utils import check_duplicates
from app.image_utils import preprocess_image
from dotenv import load_dotenv
from google import genai
import os
import json
import time

load_dotenv()

_api_key = os.getenv("GEMINI_API_KEY")
_client = genai.Client(api_key=_api_key)

MODEL_NAME = "gemini-3.6-flash"


def build_prompt(subject_name: str, image_count: int) -> str:
    """과목명과 이미지 개수를 받아서 판정 프롬프트를 만든다."""
    return f"""
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

confidence 판단 기준:
- high: 사진이 선명하고, 수행 흔적(또는 백지 상태)이 명확하여 판정에 의심의 여지가 거의 없음
- medium: 대체로 판단 가능하지만 일부 애매한 부분이 있음
- low: 수행 흔적이 애매하거나, 사진 상태/각도/일부 가림 등으로 판정에 자신이 없음

너의 판단이 애매하거나 여러 해석이 가능하다고 느껴질 때는
PASS나 FAIL을 무리하게 확정하지 말고 confidence를 low로 표시하라.
낮은 confidence는 부끄러운 것이 아니라, 정직한 판단이다.

missing_or_weak 작성 기준:
PASS로 판정하더라도, 아래와 같이 "형식적 기준에는 못 미치지만
학생에게 유리하게 PASS로 인정한" 경우에는 missing_or_weak에
구체적으로 기록하라.

예:
- 문제에 정답 선택지 표시(동그라미 등)만 있고, 실제 풀이 과정이나
  선지 소거, 채점(정답/오답 확인) 흔적이 없는 경우
- 지문에 단순 밑줄만 있고 요약이나 구조화 흔적이 없는 경우
- 극히 일부 문제만 풀려있는 경우

이런 항목이 하나도 없다면 missing_or_weak는 빈 배열로 둔다.
missing_or_weak가 채워진 PASS는 "형식은 부족하지만 통과시킨 건"이라는
의미이므로, 근거를 명확하고 구체적으로 적어라.

이번 숙제는 "{subject_name}" 과목이다.
만약 이미지가 "{subject_name}" 숙제가 아니라 다른 과목의 숙제로 보인다면,
assignment_match를 "mismatch"로 표시하고 result는 FAIL로 판정하라.

지금부터 총 {image_count}장의 이미지가 순서대로 주어진다.
각 이미지는 image_index 0부터 {image_count - 1}까지 순서대로 대응한다.

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


def _call_gemini_with_retry(contents, max_retries=3):
    """
    503(과부하)/429(쿼터) 계열 에러만 지수 백오프로 재시도한다.
    그 외 에러는 재시도해봤자 소용없으므로 바로 던진다.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            print(f"[Gemini 호출] {attempt + 1}번째 시도 시작", flush=True)
            result = _client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config={"response_mime_type": "application/json"}
            )
            print(f"[Gemini 호출] {attempt + 1}번째 시도 성공", flush=True)
            return result
        except Exception as e:
            error_text = str(e)
            is_retryable = (
                "503" in error_text
                or "UNAVAILABLE" in error_text
                or "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
            )

            if not is_retryable or attempt == max_retries - 1:
                print(f"[재시도 종료] {attempt + 1}번째 시도 실패, 재시도 안 함 (retryable={is_retryable})", flush=True)
                raise

            wait_seconds = 5 * (2 ** attempt)
            print(f"[재시도] {attempt + 1}번째 시도 실패 (503/429 계열), {wait_seconds}초 후 재시도", flush=True)
            last_error = e
            time.sleep(wait_seconds)

    raise last_error


def validate_and_correct(entry: dict) -> dict:
    """
    AI 판정 결과에 대해 프로그램이 기본적인 모순을 검증하고 필요하면 보정한다.
    (인수인계 문서 11번 항목: AI 판단과 프로그램 검증 분리)
    """
    photo_quality = entry.get("photo_quality", {})
    assignment_match = entry.get("assignment_match", {})

    original_result = entry.get("result")
    corrected_result = original_result
    correction_reason = None

    # 규칙 1: 페이지 전체가 안 보이는데 PASS/FAIL로 확정하면 위험 -> REVIEW로 보정
    if photo_quality.get("full_page_visible") is False and original_result in ("PASS", "FAIL"):
        corrected_result = "REVIEW"
        correction_reason = "full_page_visible=false인데 PASS/FAIL로 판정되어 REVIEW로 보정함"

    # 규칙 2: 가림(obstruction)이 있는데 PASS로 확정하면 위험 -> REVIEW로 보정
    elif photo_quality.get("obstruction") is True and original_result == "PASS":
        corrected_result = "REVIEW"
        correction_reason = "obstruction=true인데 PASS로 판정되어 REVIEW로 보정함"

    # 규칙 3: 과목 불일치(mismatch)인데 PASS면 위험 -> FAIL로 보정
    elif assignment_match.get("status") == "mismatch" and original_result == "PASS":
        corrected_result = "FAIL"
        correction_reason = "assignment_match=mismatch인데 PASS로 판정되어 FAIL로 보정함"

    # 규칙 4: confidence가 low인데 PASS/FAIL로 확정하면 위험 -> REVIEW로 보정
    elif entry.get("confidence") == "low" and original_result in ("PASS", "FAIL"):
        corrected_result = "REVIEW"
        correction_reason = "confidence=low인데 PASS/FAIL로 판정되어 REVIEW로 보정함"

    entry["final_result"] = corrected_result
    entry["result_was_corrected"] = corrected_result != original_result
    entry["correction_reason"] = correction_reason

    # PASS인데 missing_or_weak가 채워져 있으면 "주의가 필요한 PASS"로 플래그
    # (선생님이 전체 PASS 목록을 훑어볼 때 우선적으로 다시 볼 수 있도록)
    missing_items = entry.get("missing_or_weak", [])
    entry["needs_attention"] = (
        corrected_result == "PASS" and bool(missing_items)
    )

    return entry


def check_homework(image_paths: list[str], subject_name: str = "국어") -> dict:
    """
    이미지 경로 리스트를 받아서 Gemini에 보내고,
    검증까지 마친 최종 결과를 반환한다.

    반환값 예:
    {
        "processing_status": "SUCCESS" 또는 "FAILED",
        "error": None 또는 에러 메시지,
        "raw_response": Gemini 원본 응답 텍스트,
        "results": [ {filename, ...판정결과, final_result, duplicate_check} ... ]
    }
    """
    if not image_paths:
        return {
            "processing_status": "FAILED",
            "error": "이미지 경로가 비어있습니다.",
            "raw_response": None,
            "results": []
        }

    try:
        duplicate_results = check_duplicates(image_paths)

        uploaded_files = []
        for idx, path in enumerate(image_paths):
            processed_path = preprocess_image(path)
            uploaded = _client.files.upload(file=processed_path)
            uploaded_files.append({
                "index": idx,
                "filename": os.path.basename(path),  # 원본 파일명 그대로 기록 (사용자에게 보여줄 이름)
                "file_obj": uploaded
            })

        prompt = build_prompt(subject_name, len(uploaded_files))

        contents = [prompt]
        for item in uploaded_files:
            contents.append(item["file_obj"])

        response = _call_gemini_with_retry(contents)

        raw_text = response.text
        parsed = json.loads(raw_text)

        # image_index -> 파일명 매칭 + 검증 보정 적용
        final_results = []
        for entry in parsed:
            idx = entry.get("image_index")
            filename = uploaded_files[idx]["filename"] if idx is not None and idx < len(uploaded_files) else "알 수 없음"
            entry["filename"] = filename
            entry = validate_and_correct(entry)
            entry["duplicate_check"] = duplicate_results.get(
                filename,
                {"duplicate_status": "UNCERTAIN", "matched_with": None, "distance": None}
            )
            final_results.append(entry)

        return {
            "processing_status": "SUCCESS",
            "error": None,
            "raw_response": raw_text,
            "results": final_results
        }

    except Exception as e:
        # API 오류와 AI 판정 결과를 분리 (인수인계 문서 11번 항목)
        return {
            "processing_status": "FAILED",
            "error": str(e),
            "raw_response": None,
            "results": []
        }