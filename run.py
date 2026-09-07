from functools import wraps

from flask import Flask, jsonify, request, render_template_string, redirect, session, url_for
from app.ai_engine import check_homework
from app.submission_utils import save_submission, get_all_submissions, get_submissions_by_student
import os
import glob

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-in-render")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

TEACHER_PASSWORD = os.environ.get("TEACHER_PASSWORD")


@app.errorhandler(413)
def request_entity_too_large(error):
    return render_template_string(
        """
        <!DOCTYPE html>
        <html lang="ko">
        <head><meta charset="UTF-8"><title>업로드 오류</title></head>
        <body style="max-width: 480px; margin: 48px auto; padding: 0 24px; font-family: sans-serif;">
          <h1>업로드 용량이 너무 큽니다</h1>
          <p>한 번에 업로드할 수 있는 파일 크기는 50MB까지입니다.</p>
          <a href="/">다시 업로드</a>
        </body>
        </html>
        """
    ), 413

DATA_DIR = os.environ.get("DATA_DIR", "data")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")


def teacher_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("is_teacher") is not True:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if TEACHER_PASSWORD and password == TEACHER_PASSWORD:
            session["is_teacher"] = True
            return redirect(url_for("submissions"))
        error = "비밀번호가 올바르지 않습니다."

    return render_template_string(
        """
        <!DOCTYPE html>
        <html lang="ko">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>선생님 로그인</title>
          <style>
            :root {
              --color-primary: #29466B;
              --color-background: #FAFAF8;
              --color-border: #E2DED4;
            }
            * { box-sizing: border-box; }
            body {
              background: var(--color-background);
              color: #1C1C1A;
              font-family: Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
              margin: 0;
            }
            .login-page {
              max-width: 360px;
              min-height: 100vh;
              margin: 0 auto;
              padding: 48px 24px;
              display: flex;
              flex-direction: column;
              justify-content: center;
            }
            .login-title {
              font-size: 28px;
              line-height: 1.3;
              margin: 0 0 32px;
            }
            .login-label {
              display: block;
              font-size: 14px;
              line-height: 1.4;
              margin-bottom: 8px;
            }
            .login-input {
              width: 100%;
              min-height: 44px;
              border: 1px solid var(--color-border);
              border-radius: 4px;
              padding: 12px;
              background: #FFFFFF;
              color: inherit;
              font: inherit;
            }
            .login-input:focus {
              border-color: var(--color-primary);
              outline: 2px solid var(--color-primary);
              outline-offset: 0;
            }
            .login-error {
              color: #B3261E;
              font-size: 14px;
              line-height: 1.4;
              margin: 8px 0 0;
            }
            .login-button {
              width: 100%;
              min-height: 44px;
              margin-top: 24px;
              padding: 0 24px;
              border: 0;
              border-radius: 4px;
              background: var(--color-primary);
              color: #FFFFFF;
              font: inherit;
              font-weight: 600;
              cursor: pointer;
            }
            @media (max-width: 480px) {
              .login-page { padding: 32px 24px; }
              .login-button { min-height: 48px; }
            }
          </style>
        </head>
        <body>
          <main class="login-page">
            <h1 class="login-title">선생님 로그인</h1>
            <form method="POST">
              <label class="login-label" for="password">비밀번호</label>
              <input class="login-input" id="password" name="password" type="password" required autofocus>
              {% if error %}<p class="login-error">{{ error }}</p>{% endif %}
              <button class="login-button" type="submit">로그인</button>
            </form>
          </main>
        </body>
        </html>
        """,
        error=error,
    )


@app.route("/logout")
def logout():
    session.pop("is_teacher", None)
    return redirect(url_for("login"))


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
      <label>학번 (선택)</label>
      <input type="text" name="student_id" placeholder="예: 20315">
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
  .idnote {
    margin: 6px 0 0;
    font-size: 13px;
    color: var(--review);
  }
  .idnote.mismatch {
    color: var(--fail);
    font-weight: 600;
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
  <p class="meta">{{ submitted_at }} 제출{% if student_id %} · 학번 {{ student_id }}{% endif %}</p>

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
      {% if r.student_id_match == "MISMATCH" %}
      <p class="idnote mismatch">⚠ 학번 불일치 — 다른 학생 사진일 수 있습니다</p>
      {% elif r.student_id_match == "UNCERTAIN" %}
      <p class="idnote">학번 판독 불가 — 확인 필요</p>
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
    student_id = request.form.get("student_id", "").strip()
    assignment_name = request.form.get("assignment_name", "").strip()

    if not student_name or not assignment_name:
        return jsonify({"error": "학생 이름과 숙제명을 입력해주세요."}), 400

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    saved_paths = []
    for file in files:
        save_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(save_path)
        saved_paths.append(save_path)

    result = check_homework(saved_paths, subject_name="국어", student_id=student_id)

    submission_record = save_submission(
        student_name=student_name,
        subject_name="국어",
        assignment_name=assignment_name,
        check_result=result,
        student_id=student_id,
    )

    past_submissions = [
        s for s in get_submissions_by_student(student_name)
        if s["submission_id"] != submission_record["submission_id"]
    ]

    if request.args.get("format") == "json":
        response = dict(result)
        response["submission_id"] = submission_record["submission_id"]
        response["student_name"] = student_name
        response["student_id"] = student_id
        response["assignment_name"] = assignment_name
        return jsonify(response)

    return render_template_string(
        RESULT_PAGE_HTML,
        student_name=student_name,
        student_id=student_id,
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
    image_paths = sorted(glob.glob(os.path.join(DATA_DIR, "*.jpg")))
    result = check_homework(image_paths, subject_name="국어")
    return jsonify(result)


SUBMISSION_COMPONENTS = """
{% macro StatusStamp(status) -%}
  <span class="status-stamp {{ status }}">{{ status }}</span>
{%- endmacro %}
{% macro SubmissionTable(rows, detail=False) -%}
  <table class="submission-table">
    <thead>
      <tr>
        {% if detail %}
        <th>제출 시간</th>
        <th>판정</th>
        <th>needs_attention</th>
        <th>student_id_match</th>
        {% else %}
        <th>학생 이름</th>
        <th>학생 ID</th>
        <th>최신 판정</th>
        <th>확인 필요</th>
        <th>중복 가능성</th>
        <th>마지막 제출</th>
        {% endif %}
      </tr>
    </thead>
    <tbody>
      {% for row in rows %}
      <tr>
        {% if detail %}
        <td class="submitted-at">{{ row.submitted_at }}</td>
        <td>{{ StatusStamp(row.status) if row.status else '-' }}</td>
        <td>{% if row.needs_attention %}<span class="attention">needs_attention</span>{% endif %}</td>
        <td class="student-id">{{ row.student_id_match or '-' }}</td>
        {% else %}
        <td><a class="student-link" href="{{ url_for('submissions_by_student', student_name=row.student_name) }}">{{ row.student_name }}</a></td>
        <td class="student-id">{{ row.student_id or '-' }}</td>
        <td>{{ StatusStamp(row.status) if row.status else '-' }}</td>
        <td>{% if row.needs_attention %}<span class="attention">needs_attention</span>{% endif %}</td>
        <td>{% if row.has_duplicate %}<span class="duplicate">{{ row.duplicate_text }}</span>{% endif %}</td>
        <td class="submitted-at">{{ row.submitted_at }}</td>
        {% endif %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
{%- endmacro %}
{% macro EmptyState() -%}
  <p class="empty-state">아직 제출된 과제가 없습니다.</p>
{%- endmacro %}
"""


SUBMISSIONS_DASHBOARD_HTML = SUBMISSION_COMPONENTS + """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>제출 현황</title>
  <style>
    :root {
      --ink: #1C1C1A;
      --muted: #6E6B62;
      --rule: #DDD8CB;
      --paper: #F7F6F2;
      --pass: #2F6B4A;
      --review: #A6752E;
      --fail: #A23B32;
      --attention: #FFF5DF;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .dashboard {
      max-width: 1120px;
      margin: 0 auto;
      padding: 48px 32px 64px;
    }
    .dashboard-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 40px;
    }
    h1 {
      margin: 0;
      font-family: "Noto Serif KR", Georgia, serif;
      font-size: 30px;
      line-height: 1.3;
    }
    .logout {
      color: var(--muted);
      font-size: 14px;
      text-decoration: none;
      white-space: nowrap;
    }
    .logout:hover, .logout:focus-visible { color: var(--ink); }
    .summary {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      border-top: 1px solid var(--rule);
      border-bottom: 1px solid var(--rule);
      margin-bottom: 32px;
    }
    .summary-item {
      min-width: 0;
      padding: 16px 20px;
      border-right: 1px solid var(--rule);
    }
    .summary-item:last-child { border-right: 0; }
    .summary-label {
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }
    .summary-value {
      display: block;
      font-size: 24px;
      font-weight: 600;
    }
    .submission-table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    .submission-table th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0;
      padding: 0 16px 12px;
      text-align: left;
    }
    .submission-table td {
      border-top: 1px solid var(--rule);
      padding: 18px 16px;
      vertical-align: middle;
      overflow-wrap: anywhere;
    }
    .student-link {
      color: var(--ink);
      font-weight: 600;
      text-decoration: none;
    }
    .student-link:hover, .student-link:focus-visible { text-decoration: underline; }
    .student-id, .submitted-at {
      color: var(--muted);
      font-size: 14px;
    }
    .status-stamp {
      display: inline-block;
      border: 2px solid currentColor;
      border-radius: 2px;
      background: transparent;
      font-family: "Noto Serif KR", Georgia, serif;
      font-size: 13px;
      line-height: 1;
      padding: 6px 8px;
    }
    .status-stamp.PASS { color: var(--pass); }
    .status-stamp.REVIEW { color: var(--review); }
    .status-stamp.FAIL { color: var(--fail); }
    .attention {
      display: inline-block;
      background: var(--attention);
      color: var(--review);
      font-size: 13px;
      padding: 6px 8px;
    }
    .duplicate {
      color: var(--review);
      font-size: 13px;
      line-height: 1.4;
    }
    .empty-state {
      border-top: 1px solid var(--rule);
      border-bottom: 1px solid var(--rule);
      color: var(--muted);
      padding: 32px 16px;
      text-align: center;
    }
    @media (max-width: 760px) {
      .dashboard { padding: 32px 24px 48px; }
      .dashboard-header { margin-bottom: 28px; }
      .summary { grid-template-columns: repeat(5, minmax(72px, 1fr)); overflow: hidden; }
      .summary-item { padding: 12px 10px; }
      .summary-label { font-size: 12px; }
      .summary-value { font-size: 20px; }
      .submitted-at { display: none; }
      .submission-table th:last-child, .submission-table td:last-child { display: none; }
    }
    @media (max-width: 520px) {
      .dashboard { padding: 24px 16px 40px; }
      .dashboard-header { align-items: flex-start; }
      h1 { font-size: 25px; }
      .summary { grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 24px; }
      .summary-item { padding: 10px 5px; text-align: center; }
      .summary-label { font-size: 10px; white-space: nowrap; }
      .summary-value { font-size: 18px; }
      .submission-table thead { display: none; }
      .submission-table, .submission-table tbody, .submission-table tr, .submission-table td { display: block; width: 100%; }
      .submission-table tr { border-top: 1px solid var(--rule); padding: 16px 0; }
      .submission-table td { border: 0; padding: 3px 0; }
      .submission-table td:first-child { padding-bottom: 6px; }
      .student-link { font-size: 16px; }
      .student-id { display: block; }
      .status-stamp { margin-bottom: 3px; }
      .attention, .duplicate { margin-top: 4px; }
    }
  </style>
</head>
<body>
  <main class="dashboard">
    <header class="dashboard-header">
      <h1>제출 현황</h1>
      <a class="logout" href="{{ url_for('logout') }}">로그아웃</a>
    </header>
    {% if rows %}
      <section class="summary" aria-label="제출 요약">
        <div class="summary-item"><span class="summary-label">전체</span><strong class="summary-value">{{ summary.total }}</strong></div>
        <div class="summary-item"><span class="summary-label">PASS</span><strong class="summary-value">{{ summary.PASS }}</strong></div>
        <div class="summary-item"><span class="summary-label">REVIEW</span><strong class="summary-value">{{ summary.REVIEW }}</strong></div>
        <div class="summary-item"><span class="summary-label">FAIL</span><strong class="summary-value">{{ summary.FAIL }}</strong></div>
        <div class="summary-item"><span class="summary-label">needs_attention</span><strong class="summary-value">{{ summary.needs_attention }}</strong></div>
      </section>
      {{ SubmissionTable(rows) }}
    {% else %}
      {{ EmptyState() }}
    {% endif %}
  </main>
</body>
</html>
"""


STUDENT_SUBMISSIONS_HTML = SUBMISSION_COMPONENTS + """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ student_name }} 제출 기록</title>
  <style>
    :root { --ink: #1C1C1A; --muted: #6E6B62; --rule: #DDD8CB; --paper: #F7F6F2; --pass: #2F6B4A; --review: #A6752E; --fail: #A23B32; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--paper); color: var(--ink); font-family: Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { max-width: 760px; margin: 0 auto; padding: 48px 32px 64px; }
    header { margin-bottom: 32px; }
    .back-link { display: inline-block; margin-bottom: 20px; }
    h1 { margin: 0; font-family: "Noto Serif KR", Georgia, serif; font-size: 26px; line-height: 1.35; font-weight: 600; }
    a { color: var(--muted); font-size: 14px; text-decoration: none; }
    a:hover, a:focus-visible { color: var(--ink); text-decoration: underline; }
    .submission-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    .submission-table th { color: var(--muted); font-size: 12px; font-weight: 500; padding: 0 16px 12px; text-align: left; }
    .submission-table td { border-top: 1px solid var(--rule); padding: 18px 16px; vertical-align: middle; overflow-wrap: anywhere; }
    .status-stamp { display: inline-block; border: 2px solid currentColor; border-radius: 2px; background: transparent; font-family: "Noto Serif KR", Georgia, serif; font-size: 13px; line-height: 1; padding: 6px 8px; }
    .status-stamp.PASS { color: var(--pass); }
    .status-stamp.REVIEW { color: var(--review); }
    .status-stamp.FAIL { color: var(--fail); }
    .attention { display: inline-block; background: #FFF5DF; color: var(--review); font-size: 13px; padding: 6px 8px; }
    .student-id, .submitted-at { color: var(--muted); font-size: 14px; }
    @media (max-width: 520px) { main { padding: 32px 20px 48px; } h1 { font-size: 25px; } }
  </style>
</head>
<body>
  <main>
    <header>
      <a class="back-link" href="{{ url_for('submissions') }}">← 전체 목록</a>
      <h1>{{ student_name }}</h1>
    </header>
    {{ SubmissionTable(rows, detail=True) }}
  </main>
</body>
</html>
"""


def _submission_dashboard_rows(submissions):
    latest_by_student = {}
    for submission in submissions:
        student_name = submission.get("student_name", "")
        current = latest_by_student.get(student_name)
        if current is None or submission.get("submitted_at", "") > current.get("submitted_at", ""):
            latest_by_student[student_name] = submission

    rows = []
    status_order = {"REVIEW": 0, "FAIL": 1, "PASS": 2}
    for submission in latest_by_student.values():
        results = submission.get("results", [])
        statuses = [result.get("final_result") for result in results]
        status = min((value for value in statuses if value in status_order), key=status_order.get, default=None)
        has_duplicate = any(
          result.get("duplicate_check", {}).get("duplicate_status") in ("EXACT_DUPLICATE", "SIMILAR")
            for result in results
        )
        rows.append({
            "student_name": submission.get("student_name", ""),
            "student_id": submission.get("student_id", ""),
            "submitted_at": submission.get("submitted_at", ""),
            "status": status,
            "needs_attention": any(result.get("needs_attention") is True for result in results),
            "has_duplicate": has_duplicate,
            "duplicate_text": "이전 제출과 유사도가 높음" if has_duplicate else "",
        })

    grouped_rows = []
    for priority in (0, 1):
        group = [row for row in rows if (0 if row["status"] == "REVIEW" or row["has_duplicate"] else 1) == priority]
        group.sort(key=lambda row: row["submitted_at"], reverse=True)
        group.sort(key=lambda row: status_order.get(row["status"], 3))
        grouped_rows.extend(group)
    return grouped_rows


def _student_submission_rows(submissions):
    status_order = {"REVIEW": 0, "FAIL": 1, "PASS": 2}
    match_order = {"MISMATCH": 0, "UNCERTAIN": 1, "MATCH": 2}
    rows = []
    for submission in sorted(submissions, key=lambda item: item.get("submitted_at", ""), reverse=True):
        results = submission.get("results", [])
        statuses = [result.get("final_result") for result in results]
        matches = [result.get("student_id_match") for result in results]
        rows.append({
            "submitted_at": submission.get("submitted_at", ""),
            "status": min((value for value in statuses if value in status_order), key=status_order.get, default=None),
            "needs_attention": any(result.get("needs_attention") is True for result in results),
            "student_id_match": min(
                (value for value in matches if value in match_order),
                key=match_order.get,
                default=None,
            ),
        })
    return rows


@app.route("/submissions")
@teacher_required
def submissions():
    rows = _submission_dashboard_rows(get_all_submissions())
    summary = {
        "total": len(rows),
        "PASS": sum(row["status"] == "PASS" for row in rows),
        "REVIEW": sum(row["status"] == "REVIEW" for row in rows),
        "FAIL": sum(row["status"] == "FAIL" for row in rows),
        "needs_attention": sum(row["needs_attention"] for row in rows),
    }
    return render_template_string(SUBMISSIONS_DASHBOARD_HTML, rows=rows, summary=summary)

@app.route("/submissions/<student_name>")
@teacher_required
def submissions_by_student(student_name):
    records = get_submissions_by_student(student_name)
    return render_template_string(
        STUDENT_SUBMISSIONS_HTML,
        student_name=student_name,
      rows=_student_submission_rows(records),
    )


if __name__ == "__main__":
    app.run(debug=True)