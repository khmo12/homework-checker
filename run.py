from functools import wraps

from flask import Flask, jsonify, request, render_template_string, redirect, session, url_for
from app.ai_engine import check_homework
from app.submission_utils import save_submission, get_all_submissions, get_submissions_by_student
import os
import glob
import re
import time
import uuid

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
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>업로드 오류</title>
          <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
        </head>
        <body class="error-page">
          <h1>업로드 용량이 너무 큽니다</h1>
          <p>한 번에 업로드할 수 있는 파일 크기는 50MB까지입니다.</p>
          <a href="/">다시 업로드</a>
        </body>
        </html>
        """
    ), 413

DATA_DIR = os.environ.get("DATA_DIR", "data")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


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
          <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
          <style>
            :root {
              --paper: var(--color-background);
              --surface: var(--color-surface);
              --ink: var(--color-text-primary);
              --ink-muted: var(--color-text-secondary);
              --rule: var(--color-border);
              --error: var(--color-error);
            }
            * { box-sizing: border-box; }
            body {
              background: var(--paper);
              color: var(--ink);
              font-family: var(--font-body);
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
              border: 1px solid var(--rule);
              border-radius: 4px;
              padding: 12px;
              background: var(--surface);
              color: inherit;
              font: inherit;
            }
            .login-input:focus {
              border-color: var(--ink);
              outline: 2px solid var(--ink);
              outline-offset: 0;
            }
            .login-error {
              color: var(--error);
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
              background: var(--ink);
              color: var(--color-surface);
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
          <main class="auth-layout login-page">
            <h1 class="login-title">선생님 로그인</h1>
            <form method="POST">
              <label class="login-label" for="password">비밀번호</label>
              <input class="input login-input" id="password" name="password" type="password" required autofocus>
              {% if error %}<p class="login-error">{{ error }}</p>{% endif %}
              <button class="button login-button" type="submit">로그인</button>
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
<link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
<style>
  :root {
    --paper: var(--color-background);
    --surface: var(--color-surface);
    --ink: var(--color-text-primary);
    --ink-muted: var(--color-text-secondary);
    --rule: var(--color-border);
    --error: var(--color-error);
    --error-surface: var(--color-surface-muted);
  }
  * { box-sizing: border-box; }
  body {
    background: var(--paper);
    color: var(--ink);
    font-family: var(--font-body);
    max-width: 480px;
    margin: 0 auto;
    padding: 32px 20px 48px;
  }
  h1 {
    font-family: var(--font-display);
    font-size: 25px;
    font-weight: 700;
    margin: 0 0 4px;
  }
  .sub {
    color: var(--ink-muted);
    font-size: 14px;
    margin: 0 0 32px;
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
    min-height: 44px;
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
  .upload-label {
    display: flex;
    min-height: 120px;
    align-items: center;
    justify-content: center;
    margin: 0;
    border: 2px dotted var(--rule);
    color: var(--ink-muted);
    cursor: pointer;
    text-align: center;
  }
  .upload-label:focus-within {
    border-color: var(--ink);
    outline: 2px solid var(--ink);
    outline-offset: 2px;
  }
  .upload-label input {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
  }
  .upload-copy { padding: 20px; }
  .upload-copy strong {
    display: block;
    color: var(--ink);
    font-size: 15px;
    margin-bottom: 4px;
  }
  .file-summary[hidden], .error-banner[hidden], .loading[hidden] { display: none; }
  .file-name { overflow-wrap: anywhere; }
  .error-banner {
    margin: 20px 0 0;
    padding: 14px 16px;
    border-left: 3px solid var(--error);
    background: var(--error-surface);
    color: var(--error);
    font-size: 14px;
    line-height: 1.5;
  }
  .retry-button {
    width: auto;
    min-height: 44px;
    margin: 12px 0 0;
    padding: 0 16px;
    background: transparent;
    border: 1px solid currentColor;
    color: var(--error);
    font-size: 14px;
  }
  .loading {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 20px 0 0;
    color: var(--ink-muted);
    font-size: 14px;
    line-height: 1.5;
  }
  .spinner {
    width: 18px;
    height: 18px;
    flex: 0 0 18px;
    border: 2px solid var(--rule);
    border-top-color: var(--ink);
    border-radius: 50%;
    animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  button {
    margin-top: 12px;
    width: 100%;
    min-height: 48px;
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
  button:disabled { cursor: not-allowed; opacity: .42; }
  button:not(:disabled):hover { opacity: 0.88; }
  .secondary-fields { margin-top: 24px; }
  .secondary-fields summary {
    color: var(--ink-muted);
    cursor: pointer;
    font-size: 13px;
    min-height: 44px;
    padding: 12px 0;
  }
  .secondary-fields[open] summary { margin-bottom: 12px; }
  @media (min-width: 481px) {
    body { padding-top: 48px; }
  }
</style>
</head>
<body class="student-page">
  <h1>숙제 사진 업로드</h1>
  <p class="sub">숙제 사진을 올려주세요</p>
  <form id="upload-form" method="POST" action="/upload" enctype="multipart/form-data">
    <div class="field">
      <label for="student-id">학생 ID (선택)</label>
      <input class="input" id="student-id" type="text" name="student_id" placeholder="예: 20315" autocomplete="off">
    </div>
    <div class="field">
      <label class="file-upload-zone upload-label" for="photos">
        <span id="upload-copy" class="upload-copy"><strong>사진을 선택해주세요</strong><span>여러 장 선택 가능</span></span>
        <input id="photos" type="file" name="photos" accept="image/*" multiple required>
      </label>
    </div>
    <details class="secondary-fields">
      <summary>제출 정보 입력</summary>
      <div class="field">
        <label for="student-name">학생 이름</label>
        <input class="input" id="student-name" type="text" name="student_name" required>
      </div>
      <div class="field">
        <label for="assignment-name">숙제명</label>
        <input class="input" id="assignment-name" type="text" name="assignment_name" required>
      </div>
    </details>
    <div id="error-banner" class="error-banner" role="alert" hidden>
      <div>일시적인 오류가 발생했습니다. 다시 시도해주세요.</div>
      <button id="retry-button" class="button retry-button" type="button">다시 시도</button>
    </div>
    <div id="loading" class="loading" role="status" aria-live="polite" hidden>
      <span class="spinner" aria-hidden="true"></span>
      <span>채점 중입니다. 최대 1~2분 정도 걸릴 수 있어요.</span>
    </div>
    <button id="submit-button" class="button loading-button" type="submit" disabled>제출하고 검사하기</button>
  </form>
  <script>
    const form = document.getElementById('upload-form');
    const fileInput = document.getElementById('photos');
    const uploadCopy = document.getElementById('upload-copy');
    const submitButton = document.getElementById('submit-button');
    const errorBanner = document.getElementById('error-banner');
    const retryButton = document.getElementById('retry-button');
    const loading = document.getElementById('loading');
    const controls = form.querySelectorAll('input, button, summary');
    let submitting = false;

    function updateFileSummary() {
      const files = Array.from(fileInput.files);
      if (!files.length) {
        uploadCopy.innerHTML = '<strong>사진을 선택해주세요</strong><span>여러 장 선택 가능</span>';
        return;
      }
      uploadCopy.innerHTML = '<span class="file-name"></span><br><span>사진 ' + files.length + '장</span>';
      uploadCopy.querySelector('.file-name').textContent = files[0].name;
    }

    function updateSubmitState() {
      submitButton.disabled = submitting || !form.checkValidity();
    }

    function setSubmitting(value) {
      submitting = value;
      controls.forEach((control) => { control.disabled = value; });
      errorBanner.hidden = true;
      loading.hidden = !value;
      updateSubmitState();
    }

    fileInput.addEventListener('change', () => {
      updateFileSummary();
      updateSubmitState();
    });
    form.addEventListener('input', updateSubmitState);
    retryButton.addEventListener('click', () => {
      errorBanner.hidden = true;
      updateSubmitState();
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (submitting || !form.checkValidity()) return;
      const formData = new FormData(form);
      setSubmitting(true);
      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: formData,
        });
        if (!response.ok) throw new Error('upload failed');
        document.documentElement.innerHTML = await response.text();
      } catch (error) {
        setSubmitting(false);
        errorBanner.hidden = false;
      }
    });
    updateSubmitState();
  </script>
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
<link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
<style>
  :root {
    --ds-color-canvas: var(--color-background);
    --ds-color-surface: var(--color-surface);
    --ds-color-ink: var(--color-text-primary);
    --ds-color-muted: var(--color-text-secondary);
    --ds-color-rule: var(--color-border);
    --ds-color-pass: var(--color-success);
    --ds-color-review: var(--color-warning);
    --ds-color-fail: var(--color-error);
    --ds-color-warning-surface: var(--color-surface-muted);
    --ds-font-body: var(--font-body);
    --ds-font-display: var(--font-display);
    --ds-text-sm: 13px;
    --ds-text-md: 15px;
    --ds-text-lg: 26px;
    --ds-space-1: 6px;
    --ds-space-2: 10px;
    --ds-space-3: 16px;
    --ds-space-4: 24px;
    --ds-space-5: 36px;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--ds-color-canvas);
    color: var(--ds-color-ink);
    font-family: var(--ds-font-body);
    max-width: 560px;
    margin: 0 auto;
    padding: var(--ds-space-5) var(--ds-space-3) 64px;
  }
  h1 {
    font-family: var(--ds-font-display);
    font-size: var(--ds-text-lg);
    font-weight: 700;
    line-height: 1.35;
    margin: 0 0 var(--ds-space-1);
  }
  .meta {
    color: var(--ds-color-muted);
    font-size: var(--ds-text-sm);
    line-height: 1.5;
    margin: 0 0 var(--ds-space-1);
  }
  .history {
    color: var(--ds-color-muted);
    font-size: var(--ds-text-sm);
    line-height: 1.5;
    margin: var(--ds-space-2) 0 0;
    padding-left: var(--ds-space-3);
  }
  .history li { margin-bottom: 2px; }

  .error-block {
    margin-top: var(--ds-space-4);
    padding: var(--ds-space-3) 0 var(--ds-space-3) var(--ds-space-3);
    border-left: 3px solid var(--ds-color-fail);
  }
  .error-block .title {
    color: var(--ds-color-fail);
    font-weight: 600;
    margin: 0 0 var(--ds-space-1);
  }
  .error-block .detail {
    color: var(--ds-color-muted);
    font-size: var(--ds-text-sm);
    margin: 0;
  }

  .results { margin-top: var(--ds-space-5); }
  .row {
    padding: var(--ds-space-3) 0 var(--ds-space-3) var(--ds-space-3);
    border-top: 1px solid var(--ds-color-rule);
  }

  .row-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--ds-space-2);
    margin-bottom: var(--ds-space-2);
  }
  .status-stamp {
    display: inline-block;
    flex: 0 0 auto;
    border: 2px solid currentColor;
    border-radius: 2px;
    background: transparent;
    font-family: var(--ds-font-display);
    font-size: var(--ds-text-sm);
    font-weight: 700;
    line-height: 1;
    padding: 7px 9px;
  }
  .status-stamp.PASS { color: var(--ds-color-pass); }
  .status-stamp.REVIEW { color: var(--ds-color-review); }
  .status-stamp.FAIL { color: var(--ds-color-fail); }
  .filename {
    min-width: 0;
    color: var(--ds-color-muted);
    font-size: var(--ds-text-sm);
    overflow-wrap: anywhere;
    text-align: right;
  }
  .grading-note {
    margin-top: var(--ds-space-2);
    padding: var(--ds-space-2) var(--ds-space-3);
    border-left: 2px solid var(--ds-color-rule);
    background: var(--ds-color-surface);
  }
  .reason {
    font-family: var(--ds-font-display);
    font-size: var(--ds-text-md);
    line-height: 1.6;
    margin: 0;
  }
  .weak {
    margin: var(--ds-space-2) 0 0;
    padding-left: var(--ds-space-3);
    color: var(--ds-color-muted);
    font-size: var(--ds-text-sm);
    line-height: 1.6;
  }
  .warning-banner {
    margin: var(--ds-space-3) 0 0;
    padding: var(--ds-space-2) var(--ds-space-3);
    border-left: 3px solid var(--ds-color-review);
    background: var(--ds-color-warning-surface);
    color: var(--ds-color-review);
    font-size: var(--ds-text-sm);
    line-height: 1.5;
  }
  .duplicate-note {
    margin: var(--ds-space-2) 0 0;
    color: var(--ds-color-review);
    font-size: var(--ds-text-sm);
    line-height: 1.5;
  }
  .idnote {
    margin: var(--ds-space-1) 0 0;
    color: var(--ds-color-review);
    font-size: var(--ds-text-sm);
  }
  .idnote.mismatch {
    color: var(--ds-color-fail);
    font-weight: 600;
  }

  .footer {
    margin-top: var(--ds-space-5);
    padding-top: var(--ds-space-3);
    border-top: 1px solid var(--ds-color-rule);
  }
  .footer a {
    color: var(--ds-color-ink);
    font-size: var(--ds-text-sm);
  }
  @media (max-width: 480px) {
    body { padding: var(--ds-space-4) var(--ds-space-3) 48px; }
    h1 { font-size: 23px; }
    .row-head { align-items: flex-start; flex-direction: column; }
    .filename { text-align: left; }
  }
</style>
</head>
<body class="result-page">
  <h1>{{ student_name }} — {{ assignment_name }}</h1>
  <p class="meta">{{ submitted_at }} 제출 · 사진 {{ results|length }}장{% if student_id %} · 학번 {{ student_id }}{% endif %}</p>

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
        <span class="status-stamp {{ r.final_result }}">
          {{ r.final_result }}
        </span>
        <span class="filename">{{ r.filename }}</span>
      </div>
      <div class="grading-note">
        <p class="reason">{{ r.reason }}</p>
        {% if r.missing_or_weak %}
        <ul class="weak">
          {% for m in r.missing_or_weak %}
          <li>{{ m }}</li>
          {% endfor %}
        </ul>
        {% endif %}
      </div>
      {% if r.needs_attention %}
      <div class="status-banner warning-banner" role="note">선생님 확인 권장</div>
      {% endif %}
      {% if r.duplicate_check.duplicate_status != "UNIQUE" %}
      <p class="duplicate-note">
        {% if r.duplicate_check.duplicate_status == "EXACT_DUPLICATE" %}
        중복 가능성 있음
        {% else %}
        이전 제출과 유사도가 높음
        {% endif %}
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
    upload_started = time.perf_counter()
    print("[PERF] /upload START", flush=True)
    files = request.files.getlist("photos")

    if not files or files[0].filename == "":
        print(f"[PERF] /upload END elapsed={time.perf_counter() - upload_started:.2f}s", flush=True)
        return jsonify({"error": "선택된 파일이 없습니다."}), 400

    student_name = request.form.get("student_name", "").strip()
    student_id = request.form.get("student_id", "").strip()
    assignment_name = request.form.get("assignment_name", "").strip()

    if not student_name or not assignment_name:
        print(f"[PERF] /upload END elapsed={time.perf_counter() - upload_started:.2f}s", flush=True)
        return jsonify({"error": "학생 이름과 숙제명을 입력해주세요."}), 400

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    local_save_started = time.perf_counter()
    print("[PERF] local file save START", flush=True)
    extensions = [
        os.path.splitext(os.path.basename(file.filename))[1].lower()
        for file in files
    ]
    if any(extension not in ALLOWED_IMAGE_EXTENSIONS for extension in extensions):
        print(f"[PERF] local file save END elapsed={time.perf_counter() - local_save_started:.2f}s", flush=True)
        print(f"[PERF] /upload END elapsed={time.perf_counter() - upload_started:.2f}s", flush=True)
        return jsonify({"error": "지원되지 않는 이미지 형식입니다."}), 400

    saved_paths = []
    for index, (file, extension) in enumerate(zip(files, extensions)):
        local_filename = f"{uuid.uuid4().hex}_{index}{extension}"
        save_path = os.path.join(UPLOAD_FOLDER, local_filename)
        file.save(save_path)
        saved_paths.append(save_path)
    print(f"[PERF] local file save END elapsed={time.perf_counter() - local_save_started:.2f}s", flush=True)

    result = check_homework(saved_paths, subject_name="국어", student_id=student_id)

    save_submission_started = time.perf_counter()
    print("[PERF] save_submission START", flush=True)
    submission_record = save_submission(
        student_name=student_name,
        subject_name="국어",
        assignment_name=assignment_name,
        check_result=result,
        student_id=student_id,
        source_paths=saved_paths,
    )
    print(f"[PERF] save_submission END elapsed={time.perf_counter() - save_submission_started:.2f}s", flush=True)

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
        print(f"[PERF] /upload END elapsed={time.perf_counter() - upload_started:.2f}s", flush=True)
        return jsonify(response)

    print(f"[PERF] /upload END elapsed={time.perf_counter() - upload_started:.2f}s", flush=True)
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
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <style>
    :root {
      --ink: var(--color-text-primary);
      --ink-muted: var(--color-text-secondary);
      --rule: var(--color-border);
      --paper: var(--color-background);
      --pass: var(--color-success);
      --review: var(--color-warning);
      --fail: var(--color-error);
      --attention: var(--color-surface-muted);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: var(--font-body);
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
      font-family: var(--font-display);
      font-size: 30px;
      line-height: 1.3;
    }
    .logout {
      color: var(--ink-muted);
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
      color: var(--ink-muted);
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
      color: var(--ink-muted);
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
      color: var(--ink-muted);
      font-size: 14px;
    }
    .status-stamp {
      display: inline-block;
      border: 2px solid currentColor;
      border-radius: 2px;
      background: transparent;
      font-family: var(--font-display);
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
      color: var(--ink-muted);
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
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 24px; }
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
  <main class="dashboard-layout dashboard">
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
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <style>
    :root { --ink: var(--color-text-primary); --ink-muted: var(--color-text-secondary); --rule: var(--color-border); --paper: var(--color-background); --pass: var(--color-success); --review: var(--color-warning); --fail: var(--color-error); }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--font-body); }
    main { max-width: 760px; margin: 0 auto; padding: 48px 32px 64px; }
    header { margin-bottom: 32px; }
    .back-link { display: inline-block; margin-bottom: 20px; }
    h1 { margin: 0; font-family: var(--font-display); font-size: 26px; line-height: 1.35; font-weight: 600; }
    a { color: var(--ink-muted); font-size: 14px; text-decoration: none; }
    a:hover, a:focus-visible { color: var(--ink); text-decoration: underline; }
    .submission-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    .submission-table th { color: var(--ink-muted); font-size: 12px; font-weight: 500; padding: 0 16px 12px; text-align: left; }
    .submission-table td { border-top: 1px solid var(--rule); padding: 18px 16px; vertical-align: middle; overflow-wrap: anywhere; }
    .status-stamp { display: inline-block; border: 2px solid currentColor; border-radius: 2px; background: transparent; font-family: var(--font-display); font-size: 13px; line-height: 1; padding: 6px 8px; }
    .status-stamp.PASS { color: var(--pass); }
    .status-stamp.REVIEW { color: var(--review); }
    .status-stamp.FAIL { color: var(--fail); }
    .attention { display: inline-block; background: var(--color-surface-muted); color: var(--review); font-size: 13px; padding: 6px 8px; }
    .student-id, .submitted-at { color: var(--ink-muted); font-size: 14px; }
    @media (max-width: 520px) {
      main { padding: 32px 20px 48px; }
      h1 { font-size: 25px; }
      .submission-table thead { display: none; }
      .submission-table, .submission-table tbody, .submission-table tr, .submission-table td { display: block; width: 100%; }
      .submission-table tr { border-top: 1px solid var(--rule); padding: 16px 0; }
      .submission-table td { border: 0; padding: 3px 0; }
      .submission-table td:first-child { padding-bottom: 6px; }
      .status-stamp { margin-bottom: 3px; }
    }
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