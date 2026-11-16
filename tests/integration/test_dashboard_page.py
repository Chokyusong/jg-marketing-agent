"""화면 골격(UI_SPEC 세 번째 판, 에디토리얼 목업): TestClient로 HTML 구조와 정적 파일을 확인한다."""

import re

import pytest

JS_FILES = ["app.js", "api.js", "state.js", "format.js", "discover.js", "analysis.js", "flow.js",
            "topbar.js", "context.js", "draft.js", "report.js", "ops.js", "job.js", "sandbox.js",
            "next.js", "panels.js", "layout.js"]


@pytest.fixture
def page(make_client):
    res = make_client(key=None).get("/")
    assert res.status_code == 200
    return res.text


def _section(page: str, start: str, end: str) -> str:
    return page.split(start, 1)[1].split(end, 1)[0]


def test_layout_parts_exist(page):
    assert "JG Marketing" in page  # 1단계 테스트와 같은 확인
    assert 'class="sidebar"' not in page  # 세 번째 판: 사이드바 없음
    assert '<header class="top">' in page
    for menu in ("DASHBOARD", "DISCOVER", "ANALYZE", "EXECUTE", "ACTIVITY", "SETTINGS"):
        assert f">{menu}<" in page
    for item in ("AI", "YOUTUBE", "BROWSER"):
        assert f'<span class="sys-name">{item}</span>' in page
    assert "INTELLIGENT CONTENT WORKFLOW" in page
    assert '<section class="progress"' in page
    for col in ("col-discover", "col-analyze", "col-execute"):
        assert f'id="{col}"' in page
    for title in ("영상 탐색", "AI 분석과 댓글 초안", "실행 및 관리", "작업 기록"):
        assert title in page
    assert 'id="activity"' in page


def test_discover_column_is_wired(page):
    assert 'role="tablist"' in page
    assert 'id="tab-keyword"' in page and 'id="tab-url"' in page
    assert re.search(r'id="q"[^>]*value="연애 고민"', page)  # 입력 없이 바로 누를 수 있다
    assert 'id="search-btn">영상 찾기 ↗<' in page
    assert 'id="period"' in page and 'id="order"' in page and 'id="max-results"' in page
    for order in ("date", "relevance", "viewCount"):
        assert f'<option value="{order}"' in page
    assert '<option value="12" selected>' in page  # config.yaml discover.max_results
    assert 'id="video-list"' in page
    assert 'id="discover-error"' in page and 'role="alert"' in page
    assert 'id="resolve-form"' in page
    assert "디자인 시연용 가상 데이터" not in page


def test_unconnected_parts_are_off_and_labelled(page):
    assert "8단계에서 연결" not in page  # 8단계에서 켠 큰 버튼·진행 단계·BROWSER 상태도
    assert "3단계에서 연결" not in page  # 3단계에서 켠 요소는 문구도 지운다
    assert "5단계에서 연결" not in page  # 5단계에서 켠 분석·AI 초안·다른 초안·승인도
    assert "6단계에서 연결" not in page  # 6단계에서 켠 요소(초안 글 상자·규칙 검사)도
    assert "4단계에서 연결" not in page  # 4단계에서 켠 위 줄 AI 상태도
    assert "7단계에서 연결" not in page  # 7단계에서 켠 오늘 통계·03칸 설정·작업 기록도
    assert '<dl class="today is-off"' not in page and '<dl class="today"' in page
    assert '<fieldset class="settings" disabled>' not in page
    assert '<button type="button" class="primary" disabled>' not in page  # 큰 버튼은 8단계에 켰다
    # 9단계: SETTINGS를 켰다(읽기 전용 설정 창을 연다)
    assert "9단계에서 연결" not in page
    assert ('<button type="button" id="settings-open" aria-haspopup="dialog" '
            'aria-controls="settings-panel">') in page


def test_no_example_numbers(page):
    today = _section(page, '<dl class="today', "</dl>")
    for value in re.findall(r"<dd>(.*?)</dd>", today, re.S):
        assert value.strip().startswith("–")
    history = _section(page, 'id="activity"', "</section>")
    assert "<td>" not in history  # 기록 줄을 박아 넣지 않는다(빈 안내 한 줄만)
    for mock_only in ("WORKFLOW STAGES", "LOCAL 01", "14:32", "DESIGN PREVIEW", "NOT LIVE DATA",
                      "101 / 120", "유튜브 1 — 내 계정"):
        assert mock_only not in page


def test_disclosure_and_profiles_from_config(page):
    assert 'data-disclosure="[광고]"' in page  # 초안 글 상자의 금색 표기(draft.js가 칠한다)
    for name in ("유튜브1", "유튜브2", "유튜브3"):
        assert name in page
    assert "@gmail" not in page


def test_no_external_assets(page):
    for src in re.findall(r'(?:src|href)="([^"#]+)"', page):
        assert src.startswith("/static/"), src


@pytest.mark.parametrize("name", JS_FILES)
def test_static_js_served(make_client, name):
    res = make_client(key=None).get(f"/static/js/{name}")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]


def test_static_css_follows_mockup(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    for token in ("--bg: #0a0a0a", "--gold: #d1b990", "--dim: #918e88", "Noto Serif KR"):
        assert token in css
    for bp in ("max-width: 1120px", "max-width: 750px"):
        assert bp in css
    assert "@import" not in css and "url(http" not in css  # 외부 글꼴 없음


def test_js_does_not_use_inner_html(make_client):
    # 영상 제목 등 바깥 글을 innerHTML로 넣지 않는다(textContent만).
    for name in JS_FILES:
        assert "innerHTML" not in make_client(key=None).get(f"/static/js/{name}").text


def test_bundled_serif_font_is_linked(page, make_client):
    assert '<link rel="stylesheet" href="/static/fonts/fonts.css" />' in page
    assert make_client(key=None).get("/static/fonts/fonts.css").status_code == 200
    font = make_client(key=None).get("/static/fonts/NotoSerifKR-Regular-subset.woff2")
    assert font.status_code == 200
    assert font.headers["content-type"] == "font/woff2"


def test_label_text_is_at_least_11px(make_client):
    # UI_SPEC 6절: 이름표 11px 이상(영상 길이, 진행 단계 이름 포함, 좁은 화면 포함).
    # 9단계에서 가장 작은 글자를 11.5px로 올렸다(본문 14px · 보조 12px 이상)
    css = make_client(key=None).get("/static/css/style.css").text
    sizes = [float(x) for x in re.findall(r"font-size:\s*([\d.]+)px", css)]
    assert sizes and min(sizes) >= 11.5
    for selector in (".duration {", ".job-steps li {"):
        rule = css.split(selector, 1)[1].split("}", 1)[0]
        assert "font-size: 11.5px" in rule


def test_broken_thumbnail_falls_back_to_empty_box(make_client):
    # 그림을 못 불러오면 img를 떼어 내 빈 자리(.thumb 배경)만 남긴다. 01·02칸이 같은 함수를 쓴다.
    client = make_client(key=None)
    fmt = client.get("/static/js/format.js").text
    body = fmt.split("export function thumbnail(video) {", 1)[1]
    assert "addEventListener('error', () => img.remove()" in body
    for name in ("discover.js", "analysis.js"):
        js = client.get(f"/static/js/{name}").text
        assert "thumbnail(video)" in js
        assert "el('img'" not in js  # 썸네일 그림은 thumbnail()만 만든다


# ---------------------------------------------------------------- 3단계: 02칸 자막 출처·붙여넣기


def test_context_rows_are_on(page):
    analyze = _section(page, 'id="col-analyze"', 'id="col-execute"')
    box = _section(analyze, 'id="context-box"', 'id="draft-box"')
    assert 'class="is-off"' not in box  # 켠 요소: 꺼짐 표시 없음
    assert "<dt>자막 출처</dt>" in box and 'id="ctx-transcript"' in box
    assert "<dt>인기 댓글</dt>" in box and 'id="ctx-comments"' in box
    assert 'id="context-error"' in box and 'role="alert"' in box
    # 분석(5단계)도 켰다: 02칸에 꺼 둔 덩어리가 없다
    assert '<div class="is-off">' not in analyze
    assert 'class="line-btn is-off"' not in analyze


def test_transcript_paste_box(page):
    box = _section(page, 'id="transcript-paste"', "</details>")
    assert page.count('<details class="paste" id="transcript-paste">') == 1  # 접어 둔 채(open 없음)
    assert "<summary>자막 붙여넣기</summary>" in box
    assert "유튜브 영상 아래 '스크립트 표시'에서 복사해 붙여 넣으세요." in box
    assert '<textarea class="field" id="transcript-text"' in box
    assert 'data-max="20000"' in box
    assert "0 / 20,000자" in box
    assert 'id="transcript-save" disabled>저장</button>' in box
    assert 'id="transcript-clear" hidden disabled>' in box


def test_context_js_wires_the_three_apis(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    for snippet in ("/context${refresh ? '?refresh=true' : ''}", "method: 'PUT'",
                    "method: 'DELETE'"):
        assert snippet in api
    js = client.get("/static/js/context.js").text
    for text in ("붙여 넣은 자막 ", "자막 없음 · 제목과 설명으로 대신", "인기 댓글 ",
                 "댓글이 막힌 영상"):
        assert text in js
    assert "api.buildContext(videoId)" in js
    assert "api.saveTranscript(videoId, text)" in js
    assert "initContext" in client.get("/static/js/app.js").text


def test_version_shows_current_stage(page):
    # 버전은 단계가 끝날 때마다 하나씩 올린다(실행 순서 3 → P → 6 → 4 → 5 → 7 → 8: 0.3.0 … 0.8.0)
    assert "V 0.9.0 — LOCAL · 9단계" in page
    assert "STAGE 9" in page


# ---------------------------------------------------------------- 6단계: 02칸 댓글 초안·규칙 검사


def test_draft_box_is_on(page):
    analyze = _section(page, 'id="col-analyze"', 'id="col-execute"')
    draft = _section(analyze, 'id="draft-box"', '<p class="note">')
    assert 'class="is-off"' not in draft.split('class="draftfooter"', 1)[0]  # 글 상자는 켜져 있다
    assert 'data-min="40"' in page and 'data-max="120"' in page  # config.yaml comment
    assert '<label for="draft-text">댓글 초안</label>' in draft
    assert 'id="draft-count">0 / 120자</span>' in draft
    assert '<textarea class="draft-input" id="draft-text"' in draft
    assert 'id="draft-mirror" aria-hidden="true"' in draft  # 표기 금색으로 칠하는 거울
    assert 'id="draft-tag">DRAFT · REVIEW REQUIRED</span>' in draft
    assert 'id="draft-checks" aria-live="polite"' in draft
    # 5단계에서 켰다: [다른 초안 생성]·[이 초안 승인](초안이 생기기 전에는 눌리지 않는다)
    another = '<button type="button" class="line-btn" id="another-btn" disabled>다른 초안 생성 ↗'
    assert another in draft
    assert 'id="approve-btn" disabled>이 초안 승인</button>' in draft
    assert "영상의 구체적 장면은 실제 자막 등 검증 가능한 근거가 있을 때만 반영합니다." in analyze


def test_disclosure_toggle_starts_on_and_locked(page):
    # 「홍보 표기」: 켠 채 잠겨 있다가 내 채널 영상(맥락 응답 own_video)일 때만 끌 수 있다
    draft = _section(page, 'id="draft-box"', 'class="draft-edit"')
    assert 'id="disclose-toggle"' in draft
    assert '<input type="checkbox" id="disclose" checked disabled />' in draft
    assert "own_video_ids" in draft  # 왜 잠겼는지 title로 알린다


def test_draft_js_checks_after_pause_and_folds_passed_items(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    assert "request('/api/validate', { method: 'POST'" in api
    assert "video_id: videoId, text" in api
    js = client.get("/static/js/draft.js").text
    assert "const DEBOUNCE_MS = 400;" in js  # 입력이 0.4초 멈추면 검사
    assert "api.validate(videoId, text)" in js
    for text in ("'CHECKED'", "'DRAFT · REVIEW REQUIRED'", "개 중 ", "개 통과", "개 모두 통과",
                 "checks-fail", "class: 'disclosure'", "normalize('NFC').trim()"):
        assert text in js
    # 통과 항목은 접어 두고(details) 실패만 펼친다
    assert "el('details'" in js and "failed.map(" in js
    assert "initDraft" in client.get("/static/js/app.js").text
    flow = client.get("/static/js/flow.js").text
    assert "v.result.passed" in flow and "규칙 검사 통과" in flow


def test_draft_styles(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    mirror = css.split(".draft-mirror .disclosure {", 1)[1].split("}", 1)[0]
    assert "var(--gold)" in mirror
    assert ".draft-input {" in css and "color: transparent" in css.split(".draft-input {", 1)[1]
    assert ".checks-fail li {" in css and ".tag.is-ok" in css


# ---------------------------------------------------------------- 5단계: 02칸 분석·AI 초안·승인


def test_report_box_is_on_with_run_button_and_five_lines(page):
    analyze = _section(page, 'id="col-analyze"', 'id="col-execute"')
    report = _section(analyze, 'id="report-box"', 'id="context-box"')
    assert "영상 맥락 분석" in report and "CONTEXT REPORT" in report
    # 영상을 고르자마자 돌지 않는다: 단추로 시작(영상을 고르기 전에는 눌리지 않는다)
    assert 'id="run-btn" disabled>분석하고 초안 만들기 ↗</button>' in report
    for phase, label in (("context", "맥락 수집"), ("analysis", "분석"), ("draft", "초안"),
                         ("check", "검사")):
        assert f'<li data-phase="{phase}">{label}</li>' in report
    assert "큰 모델은 처음에 1분쯤 걸립니다" in report  # 긴 작업 안내
    assert 'id="run-error" role="alert" hidden' in report
    for dt, dd in (("주요 주제", "an-topic"), ("핵심 고민", "an-concern"), ("영상 톤", "an-tone"),
                   ("시청자 니즈", "an-needs"), ("분석 근거", "an-evidence")):
        assert f'<dt>{dt}</dt><dd id="{dd}">' in report
    assert 'id="draft-tone"' in page  # 말투 분류(본문에는 넣지 않는다)


def test_execute_button_is_on_from_stage_8(page):
    execute = _section(page, 'id="col-execute"', 'id="activity"')
    # 8단계: 큰 버튼은 켜는 조건(승인한 초안 + 댓글 안 단 영상 + 오늘 남은 횟수)을 job.js가 본다
    button = ('<button type="button" class="primary" id="job-primary" disabled>'
              "브라우저에서 영상 열기 ↗</button>")
    assert button in execute
    assert "작업 실행은 8단계에서 연결" not in execute


def test_report_js_runs_steps_in_order_on_button_only(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    for snippet in ("`/api/analysis/${encodeURIComponent(videoId)}`, { method: 'POST' }",
                    "request('/api/drafts', { method: 'POST'", "`/api/drafts?video_id=",
                    "method: 'PATCH'", "`/api/drafts/${id}/approve`", "this.failures = failures"):
        assert snippet in api, snippet
    js = client.get("/static/js/report.js").text
    assert "$('run-btn').addEventListener('click'" in js
    # 영상을 고르면 저장된 것만 불러온다(api.analyze는 단추를 눌렀을 때만)
    select_block = js.split("if (state.selectedId !== lastSelected) {", 1)[1].split("return;", 1)[0]
    assert "restore(" in select_block and "run(" not in select_block
    assert js.index("waitForContext(videoId)") < js.index("api.analyze(videoId)") < js.index(
        "api.createDraft(videoId")
    for text in ("큰 모델은 처음에 1분쯤 걸립니다", "번째에 통과", "초", "another: true",
                 "api.updateDraft(draft.id, text)", "api.approveDraft(current.id)", "외 ",
                 "setAttribute('title'"):
        assert text in js, text
    draft = client.get("/static/js/draft.js").text
    # 9단계: 한국어 이름표(승인됨)를 앞에 따로 두고 영어 꼬리표는 짧게
    assert "export function loadDraft(draft)" in draft
    assert "'APPROVED'" in draft and "'승인됨'" in draft
    assert "말투 · " in draft
    assert "initReport" in client.get("/static/js/app.js").text
    flow = client.get("/static/js/flow.js").text
    assert "const current = approved ? 3 : video ? 2 : 1;" in flow  # 승인하면 03
    # 승인 뒤 03 문구는 8단계 job.js가 쓴다
    assert "초안 승인 완료" in client.get("/static/js/job.js").text


def test_report_lines_are_clipped_to_one_line(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    rule = css.split(".report .analysis dd {", 1)[1].split("}", 1)[0]
    for token in ("white-space: nowrap", "overflow: hidden", "text-overflow: ellipsis"):
        assert token in rule
    assert ".run-steps li.is-current" in css and ".line-btn.approve-btn" in css


# ---------------------------------------------------------------- 7단계: 오늘 통계·설정·기록


def test_today_stats_are_on_and_start_empty(page):
    today = _section(page, '<dl class="today"', "</dl>")
    for dd_id, label in (("stat-videos", "TODAY · VIDEOS"), ("stat-drafts", "DRAFTS"),
                         ("stat-posted", "POSTED"), ("stat-success", "SUCCESS")):
        assert f'<dt>{label}</dt><dd id="{dd_id}">–</dd>' in today  # 값은 화면이 API로 채운다
    assert 'id="today-note"' in page
    assert "오늘 통계 · 7단계에서 연결" not in page


def test_execute_settings_are_on(page):
    execute = _section(page, 'id="col-execute"', 'id="activity"')
    settings = _section(execute, '<div class="exec-settings"', '<div class="asidebox">')
    assert 'class="is-off"' not in settings
    assert 'data-target="sandbox"' in settings and 'data-limit="10"' in settings
    assert "LOCAL CONTROL</span>" in settings and "7·8단계에서 연결" not in settings
    assert '<option value="" selected>자동 배정</option>' in settings
    for name in ("유튜브1", "유튜브2", "유튜브3"):
        assert f'<option value="{name}">{name}</option>' in settings
    # 작업 방식 두 가지: 기본은 config.yaml browser.default_target(sandbox)
    assert re.search(r'name="mode" value="youtube" />.*수동 승인 후 게시 \(권장\)', settings)
    assert re.search(r'name="mode" value="sandbox" checked />.*테스트 페이지 자동 실행', settings)
    assert "통제된 테스트 페이지에서만" in settings
    # 일일 제한은 설정값 이하로만 고른다
    assert re.findall(r'<option value="(\d+)"[^>]*>최대 \d+건', settings) == ["10", "5", "3", "1"]
    assert '<option value="10" selected>최대 10건</option>' in settings
    assert 'id="today-count"' in settings
    # 큰 실행 버튼과 진행 단계 표시는 8단계에 켰다
    assert '<ol class="job-steps" id="job-steps" aria-label="진행 단계">' in execute


def test_daily_limit_options_follow_config(make_client):
    page = make_client(key=None, overrides={"limits": {"daily_max_comments": 3},
                                            "browser": {"default_target": "assist"}}).get("/").text
    settings = _section(page, '<div class="exec-settings"', '<div class="asidebox">')
    assert re.findall(r'<option value="(\d+)"[^>]*>최대 \d+건', settings) == ["3", "1"]
    assert 'name="mode" value="youtube" checked />' in settings  # assist → 실제 유튜브


def test_records_table_is_on(page):
    history = _section(page, 'id="activity"', "</section>")
    assert "7단계에서 연결" not in history
    # 9단계: 한국어 이름을 위에, 영어는 작게 아래에
    assert 'id="records-meta">최근 5줄 · ACTIVITY ARCHIVE<' in history
    for ko, en in (("시간", "TIME"), ("영상", "VIDEO"), ("작업", "ACTION"), ("댓글", "COMMENT"),
                   ("상태", "STATUS"), ("프로필", "PROFILE")):
        assert f'<th><span class="ko">{ko}</span><small class="en">{en}</small></th>' in history
    assert '<tbody id="records-body">' in history
    assert "아직 기록이 없습니다." in history
    assert '<col class="c-comment" />' in history


def test_ops_js_wires_the_three_apis(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    for snippet in ("`/api/profiles?target=", "`/api/records?limit=", "`/api/stats/today?"):
        assert snippet in api, snippet
    js = client.get("/static/js/ops.js").text
    for text in ("api.todayStats(ops.target, ops.dailyLimit)", "api.records(RECENT_ROWS)",
                 "const RECENT_ROWS = 5;", "timeZone: 'Asia/Seoul'", "'–'",
                 "setInterval(refreshOps", "export async function refreshOps()"):
        assert text in js, text
    assert "initOps" in client.get("/static/js/app.js").text
    report = client.get("/static/js/report.js").text
    assert report.count("refreshOps();") == 2  # 분석·초안이 끝날 때, 승인이 끝날 때
    discover = client.get("/static/js/discover.js").text
    assert "댓글 단 영상 · " in discover and "video.commented" in discover


def test_records_and_commented_styles(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    assert ".video-meta .commented {" in css and "var(--gold)" in css.split(
        ".video-meta .commented {", 1)[1].split("}", 1)[0]
    assert "table-layout: fixed" in css
    for tone in (".history td.st.is-ok b", ".history td.st.is-bad b"):
        assert tone in css


# ---------------------------------------------------------------- 8단계: 03칸 작업 상자 · BROWSER


def test_job_box_has_six_steps_and_only_needed_buttons(page):
    box = _section(page, 'id="job-box"', '<div class="hint">')
    steps = re.findall(r'<li data-step="(\d)">([^<]+)</li>', box)
    assert steps == [("0", "대기"), ("1", "프로필 실행"), ("2", "댓글 입력"), ("3", "승인 대기"),
                     ("4", "게시 완료"), ("5", "확인")]
    # 상태에 따라 필요한 것만 보인다: 작은 단추 줄과 실패 사유는 처음에 숨김
    assert 'class="job-actions" id="job-actions" hidden' in box
    for bid, text in (("job-copy", "초안 복사"), ("job-not-posted", "게시 안 함"),
                      ("job-cancel", "작업 취소")):
        assert f'id="{bid}" hidden>{text}</button>' in box
    view = 'id="job-view" href="#" target="_blank" rel="noopener noreferrer" hidden>댓글 보기 ↗'
    assert view in box
    assert 'id="job-shot"' in box and 'id="job-error" role="alert" hidden' in box
    assert 'id="job-status"' in box


def test_browser_status_is_on(page):
    top = _section(page, '<ul class="system"', "</ul>")
    assert 'id="status-browser-dot"' in top and 'id="status-browser">확인 중<' in top
    assert "8단계에서 연결" not in top


def test_job_js_wires_the_job_apis(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    for snippet in ("request('/api/jobs', {", "`/api/jobs/${encodeURIComponent(id)}`",
                    "/approve`", "/confirm`", "/cancel`", "JSON.stringify({ posted })"):
        assert snippet in api, snippet
    js = client.get("/static/js/job.js").text
    for text in ("const POLL_MS = 500;", "api.startJob(", "api.approveJob(job.id)",
                 "api.confirmJob(job.id, true)", "api.confirmJob(job.id, false)",
                 "api.cancelJob(job.id)", "navigator.clipboard.writeText(job.comment_text)",
                 "refreshOps();", "commented: { ...(v.commented || {}), [job.target]: true }",
                 "통제된 테스트 페이지에서 실행", "video.commented[target]",
                 "ops.stats.remaining <= 0", "active_job_id", "게시했어요", "게시 승인"):
        assert text in js, text
    assert "innerHTML" not in js
    assert "initJob" in client.get("/static/js/app.js").text
    topbar = client.get("/static/js/topbar.js").text
    assert "export function browserStatusText" in topbar and "renderBrowser(state)" in topbar
    flow = client.get("/static/js/flow.js").text
    assert "job.js" in flow


def test_job_box_styles(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    for rule in (".job-steps li.is-current", ".job-steps li.is-done", ".job-steps li.is-failed",
                 ".job-actions {", ".job-error {"):
        assert rule in css, rule


def test_hidden_job_buttons_stay_hidden(make_client):
    """작은 단추의 display 규칙이 hidden을 이기면 안 된다(상태마다 필요한 단추만 보인다)."""
    css = make_client(key=None).get("/static/css/style.css").text
    shown = css.index(".job-actions .line-btn {")
    hidden = css.index(".job-actions .line-btn[hidden] { display: none; }")
    assert hidden > shown


# ---------------------------------------------------------------- 실제 데이터 보정


def test_discover_has_exclude_shorts_checked_by_default(page, make_client):
    # 01칸 거르기 옆 「쇼츠 제외」 체크(config.yaml discover.exclude_shorts = 기본 켬)
    assert re.search(r'id="exclude-shorts"[^>]*checked', page)
    assert "쇼츠 제외" in page
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    assert "params.set('exclude_shorts', String(excludeShorts))" in api
    discover = client.get("/static/js/discover.js").text
    assert "excludeShorts: $('exclude-shorts')" in discover
    assert "`쇼츠 ${state.meta.shortsExcluded}개 제외`" in discover  # 결과 줄
    css = client.get("/static/css/style.css").text
    assert ".filters .shorts-toggle { flex: none; }" in css  # 같은 줄(높이가 늘지 않게)


def test_exclude_shorts_unchecked_when_config_turns_it_off(make_client):
    overrides = {"discover": {"query": "연애 고민", "max_results": 12, "exclude_shorts": False}}
    page = make_client(key=None, overrides=overrides).get("/").text
    assert re.search(r'id="exclude-shorts"[^>]*/>', page)
    assert not re.search(r'id="exclude-shorts"[^>]*checked', page)


def test_no_love_concern_shows_message_and_opens_transcript_paste(make_client):
    client = make_client(key=None)
    js = client.get("/static/js/report.js").text
    assert "const NO_CONCERN = 'no_love_concern';" in js
    assert "if (error.kind === NO_CONCERN) openTranscriptPaste();" in js
    assert "paste.open = true;" in js
    assert "'연애 고민 없음'" in js  # 분석 줄 「핵심 고민」
    # 오류 문구는 서버 문구를 그대로 띄운다(run-error)
    assert "$('run-error-msg').textContent = err.message" in js
    page = client.get("/").text
    assert 'id="transcript-paste"' in page and 'id="run-error"' in page


# ---------------------------------------------------------------- 9단계: 대시보드 완성


def test_korean_labels_come_first_and_english_is_small(page):
    nav = _section(page, '<nav class="nav"', "</nav>")
    for ko, en in (("대시보드", "DASHBOARD"), ("영상 탐색", "DISCOVER"), ("분석", "ANALYZE"),
                   ("실행", "EXECUTE"), ("기록", "ACTIVITY"), ("설정", "SETTINGS")):
        assert f'<span class="ko">{ko}</span><small class="en">{en}</small>' in nav
    assert 'class="on"' not in nav  # 지금 칸 표시는 topbar.js가 붙인다
    for ko in ("AI 모델", "유튜브", "브라우저"):
        assert f'<span class="sys-ko">{ko}</span>' in page
    today = _section(page, '<dl class="today', "</dl>")
    for ko, en in (("오늘 처리", "TODAY · VIDEOS"), ("초안", "DRAFTS"), ("게시 완료", "POSTED"),
                   ("성공률", "SUCCESS")):
        assert f'<dt class="ko">{ko}</dt><dt>{en}</dt>' in today


def test_settings_and_records_panels_are_dialogs(page):
    for panel, title, label in (("settings-panel", "settings-title", "설정 닫기"),
                                ("records-panel", "records-title", "전체 기록 닫기")):
        assert f'id="{panel}" aria-labelledby="{title}">' in page
        block = _section(page, f'id="{panel}"', "</dialog>")
        assert f'<h2 id="{title}" tabindex="-1">' in block  # 열면 제목으로 초점
        assert f'data-close aria-label="{label}"' in block  # 닫기 단추에 이름
    settings = _section(page, 'id="settings-panel"', "</dialog>")
    assert 'id="settings-body"' in settings and 'id="warmup-btn"' in settings
    records = _section(page, 'id="records-panel"', "</dialog>")
    assert 'id="records-failed-only"' in records and 'id="records-all-body"' in records
    assert '<span class="ko">캡처</span>' in records  # 실패 화면 캡처 칸
    assert 'id="records-all" aria-haspopup="dialog" aria-controls="records-panel"' in page
    for col in ("영상 탐색", "AI 분석과 댓글 초안", "실행 및 관리"):
        assert f'<h2 tabindex="-1">{col}</h2>' in page  # 메뉴로 가면 칸 제목에 초점


def test_panels_js_opens_closes_and_returns_focus(make_client):
    client = make_client(key=None)
    js = client.get("/static/js/panels.js").text
    for snippet in ("panel.showModal();", "(title || panel).focus();",
                    "panel.addEventListener('close'", "opener.focus()", "event.target === panel",
                    "api.records(ALL_ROWS)", "has_screenshot",
                    "/screenshot`", "'data-label': '댓글'", "실패 "):
        assert snippet in js, snippet
    # [모델 미리 불러오기]는 단추를 눌렀을 때만 부른다(패널을 연다고 부르지 않는다)
    assert js.count("api.warmup()") == 1
    assert "$('warmup-btn').addEventListener('click', warmup);" in js
    settings_open = js.split("$('settings-open').addEventListener('click'", 1)[1].split("});", 1)[0]
    assert "warmup" not in settings_open and "loadSettings();" in settings_open
    api = client.get("/static/js/api.js").text
    assert "settings: () => request('/api/settings')" in api
    assert "warmup: () => request('/api/llm/warmup', { method: 'POST' })" in api
    # 화면에 키 값을 그리지 않는다(있다/없다만)
    assert "key_configured" in js and "api_key" not in js


def test_next_action_highlights_one_thing_in_order(make_client):
    client = make_client(key=None)
    js = client.get("/static/js/next.js").text
    order = ["'search-btn'", "'video-list'", "'job-primary'", "'approve-btn'", "'draft-edit'"]
    for snippet in order + ["'resolve-btn'", "'transcript-paste'", "'transcript-save'", "'run-btn'",
                            "classList.add('is-next')", "is-next-hint", "WAIT_HINT"]:
        assert snippet in js, snippet
    assert "1~2분" in js  # 오래 걸리는 일에는 예상 시간
    app = client.get("/static/js/app.js").text
    assert app.rstrip().splitlines()[-1].startswith("initNext();")  # 다른 칸이 다 그린 뒤
    css = client.get("/static/css/style.css").text
    assert "button.is-next:not(:disabled)" in css and "--btn-line:" in css
    assert ".column.is-focus" in css


def test_columns_scroll_inside_when_window_is_short(make_client):
    client = make_client(key=None)
    css = client.get("/static/css/style.css").text
    assert ".workspace.is-capped .column" in css and "var(--col-max)" in css
    layout = client.get("/static/js/layout.js").text
    assert "(min-width: 1121px)" in layout and "--col-max" in layout and "ResizeObserver" in layout
    topbar = client.get("/static/js/topbar.js").text
    assert "aria-current" in topbar and "is-focus" in topbar and "preventScroll" in topbar


def test_body_and_list_text_sizes(make_client):
    css = make_client(key=None).get("/static/css/style.css").text

    def rule(selector):
        return css.split(selector, 1)[1].split("}", 1)[0]

    assert "font-size: 14px" in rule("body {")
    assert "font-size: 14px" in rule(".video-title { display")


def test_empty_loading_and_error_texts_name_the_next_step(make_client):
    client = make_client(key=None)
    discover = client.get("/static/js/discover.js").text
    for text in ("보통 1~2초 걸립니다", "[영상 찾기]를 다시 눌러 보세요", "[불러오기]",
                 "영상을 하나 고르세요"):
        assert text in discover, text
    page = client.get("/").text
    assert "아직 기록이 없습니다." in page
