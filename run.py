from flask import Flask, jsonify, request, render_template_string
from app.ai_engine import check_homework
from app.submission_utils import save_submission, get_all_submissions, get_submissions_by_student
import os
import glob

app = Flask(__name__)

UPLOAD_FOLDER = "data/uploads"

UPLOAD_FORM_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>숙제 검사기</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {
    --paper: #F7F6F2;
    --ink: #1C1C1A;
    --ink-muted: #6E6B62;
    --rule: #DDD8CB;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--paper);
    color: var(--ink);
    font-family: 'Pretendard', -apple-system, sans-serif;
    max-width: 480px;
    margin: 0 auto;
    padding: 48px 24px;
  }
  h1 {
    font-family: 'Noto Serif KR', serif;
    font-size: 26px;
    font-weight: 700;
    margin: 0 0 4px;
  }
  .sub {
    color: var(--ink-muted);
    font-size: 14px;
    margin: 0 0 36px;
  }
  label {
    display: block;
    font-size: 13px;
    color: var(--ink-muted);
    margin-bottom: 6px;
  }
  .field { margin-bottom: 20px; }
  input[type=text] {
    width: 100%;
    padding: 10px 0;
    border: none;
    border-bottom: 1px solid var(--rule);
    background: transparent;
    font-size: 16px;
    font-family: inherit;
    color: var(--ink);
    outline: none;
  }
  input[type=text]:focus { border-bottom-color: var(--ink); }
  input[type=file] {
    width: 100%;
    font-size: 14px;
    color: var(--ink-muted);
    padding: 12px 0;
    border-bottom: 1px solid var(--rule);
  }
  button {
    margin-top: 12px;
    width: 100%;
    padding: 14px;
    background: var(--ink);
    color: var(--paper);
    border: none;
    border-radius: 4px;
    font-size: 15px;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  button:hover { opacity: 0.88; }
</style>
</head>
<body>
  <h1>숙제 사진 업로드</h1>
  <p class="sub">학생 이름과 숙제명을 입력하고 사진을 3~5장 올려주세요.</p>
  <form method="POST" action="/upload" enctype="multipart/form-data">
    <div class="field">
      <label>학생 이름</label>
      <input type="text" name="student_name" required>
    </div>
    <div class="field">
      <label>숙제명</label>
      <input type="text" name="assignment_name" required>
    </div>
    <div class="field">
      <label>숙제 사진 (여러 장 선택 가능)</label>
      <input type="file" name="photos" accept="image/*" multiple required>
    </div>
    <button type="submit">제출하고 검사하기</button>
  </form>
</body>
</html>
"""

RESULT_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>검사 결과</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {
    --paper: #F7F6F2;
    --ink: #1C1C1A;
    --ink-muted: #6E6B62;
    --rule: #DDD8CB;
    --pass: #2F6B4F;
    --fail: #B3261E;
    --review: #A66A00;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--paper);
    color: var(--ink);
    font-family: 'Pretendard', -apple-system, sans-serif;
    max-width: 560px;
    margin: 0 auto;
    padding: 48px 24px 80px;
  }
  h1 {
    font-family: 'Noto Serif KR', serif;
    font-size: 26px;
    font-weight: 700;
    margin: 0 0 6px;
  }
  .meta {
    color: var(--ink-muted);
    font-size: 14px;
    margin: 0 0 4px;
  }
  .history {
    color: var(--ink-muted);
    font-size: 13px;
    margin: 12px 0 0;
    padding-left: 16px;
  }
  .history li { margin-bottom: 2px; }

  .error-block {
    margin-top: 28px;
    padding: 16px 0 16px 16px;
    border-left: 3px solid var(--fail);
  }
  .error-block .title {
    color: var(--fail);
    font-weight: 600;
    margin: 0 0 6px;
  }
  .error-block .detail {
    color: var(--ink-muted);
    font-size: 13px;
    margin: 0;
  }

  .results { margin-top: 36px; }
  .row {
    padding: 18px 0 18px 16px;
    border-top: 1px solid var(--rule);
    border-left: 3px solid var(--rule);
  }
  .row.PASS { border-left-color: var(--pass); }
  .row.FAIL { border-left-color: var(--fail); }
  .row.REVIEW { border-left-color: var(--review); }

  .row-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .status {
    font-weight: 600;
    font-size: 14px;
  }
  .status.PASS { color: var(--pass); }
  .status.FAIL { color: var(--fail); }
  .status.REVIEW { color: var(--review); }
  .filename {
    color: var(--ink-muted);
    font-size: 13px;
  }
  .flag {
    color: var(--fail);
    font-size: 13px;
  }
  .reason {
    font-size: 15px;
    line-height: 1.6;
    margin: 0;
  }
  .weak {
    margin: 10px 0 0;
    padding-left: 18px;
    color: var(--ink-muted);
    font-size: 13px;
    line-height: 1.6;
  }
  .dup {
    margin: 10px 0 0;
    font-size: 13px;
    color: var(--review);
  }

  .footer {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid var(--rule);
  }
  .footer a {
    color: var(--ink);
    font-size: 14px;
  }
</style>
</head>
<body>
  <h1>{{ student_name }} — {{ assignment_name }}</h1>
  <p class="meta">{{ submitted_at }} 제출</p>

  {% if past_submissions %}
  <p class="meta">이전 제출 {{ past_submissions|length }}건</p>
  <ul class="history">
  {% for s in past_submissions %}
    <li>{{ s.submitted_at }} · {{ s.assignment_name }}
      {% if s.processing_status != "SUCCESS" %}(검사 실패){% endif %}
    </li>
  {% endfor %}
  </ul>
  {% endif %}

  {% if processing_status != "SUCCESS" %}
  <div class="error-block">
    <p class="title">검사에 실패했습니다. 잠시 후 다시 제출해주세요.</p>
    <p class="detail">{{ error }}</p>
  </div>
  {% endif %}

  <div class="results">
  {% for r in results %}
    <div class="row {{ r.final_result }}">
      <div class="row-head">
        <span class="status {{ r.final_result }}">
          {% if r.final_result == "PASS" %}통과{% elif r.final_result == "FAIL" %}미흡{% else %}검토 필요{% endif %}
        </span>
        <span class="filename">{{ r.filename }}</span>
      </div>
      <p class="reason">{{ r.reason }}</p>
      {% if r.needs_attention %}
      <p class="flag">✎ 선생님 확인 권장</p>
      {% endif %}
      {% if r.missing_or_weak %}
      <ul class="weak">
        {% for m in r.missing_or_weak %}
        <li>{{ m }}</li>
        {% endfor %}
      </ul>
      {% endif %}
      {% if r.duplicate_check.duplicate_status != "UNIQUE" %}
      <p class="dup">중복 의심: {{ r.duplicate_check.duplicate_status }}
        {% if r.duplicate_check.matched_with %}({{ r.duplicate_check.matched_with }}와 유사){% endif %}
      </p>
      {% endif %}
    </div>
  {% endfor %}
  </div>

  <div class="footer">
    <a href="/">다시 업로드</a>
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(UPLOAD_FORM_HTML)


@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("photos")

    if not files or files[0].filename == "":
        return jsonify({"error": "선택된 파일이 없습니다."}), 400

    student_name = request.form.get("student_name", "").strip()
    assignment_name = request.form.get("assignment_name", "").strip()

    if not student_name or not assignment_name:
        return jsonify({"error": "학생 이름과 숙제명을 입력해주세요."}), 400

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    saved_paths = []
    for file in files:
        save_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(save_path)
        saved_paths.append(save_path)

    result = check_homework(saved_paths, subject_name="국어")

    submission_record = save_submission(
        student_name=student_name,
        subject_name="국어",
        assignment_name=assignment_name,
        check_result=result,
    )

    past_submissions = [
        s for s in get_submissions_by_student(student_name)
        if s["submission_id"] != submission_record["submission_id"]
    ]

    if request.args.get("format") == "json":
        response = dict(result)
        response["submission_id"] = submission_record["submission_id"]
        response["student_name"] = student_name
        response["assignment_name"] = assignment_name
        return jsonify(response)

    return render_template_string(
        RESULT_PAGE_HTML,
        student_name=student_name,
        assignment_name=assignment_name,
        submitted_at=submission_record["submitted_at"],
        results=result.get("results", []),
        processing_status=result.get("processing_status"),
        error=result.get("error"),
        past_submissions=past_submissions,
    )


@app.route("/check-test")
def check_test():
    """기존 테스트용 라우트 (data 폴더 사진으로 확인)"""
    image_paths = sorted(glob.glob("data/*.jpg"))
    result = check_homework(image_paths, subject_name="국어")
    return jsonify(result)


@app.route("/submissions")
def submissions():
    """제출 기록 전체 확인용 테스트 라우트"""
    return jsonify(get_all_submissions())


if __name__ == "__main__":
    app.run(debug=True)