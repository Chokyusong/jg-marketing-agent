"""화면 골격(UI_SPEC 세 번째 판, 에디토리얼 목업): TestClient로 HTML 구조와 정적 파일을 확인한다."""

import re

import pytest

JS_FILES = ["app.js", "api.js", "state.js", "format.js", "discover.js", "analysis.js", "flow.js",
            "topbar.js", "context.js", "draft.js"]


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
    for label in ("5단계에서 연결", "7단계에서 연결", "8단계에서 연결"):
        assert label in page
    assert "3단계에서 연결" not in page  # 3단계에서 켠 요소는 문구도 지운다
    assert "6단계에서 연결" not in page  # 6단계에서 켠 요소(초안 글 상자·규칙 검사)도
    assert "4단계에서 연결" not in page  # 4단계에서 켠 위 줄 AI 상태도
    assert '<dl class="today is-off"' in page
    assert '<fieldset class="settings" disabled>' in page
    assert '<button type="button" class="primary" disabled>' in page
    assert '<button type="button" disabled title="9단계에서 연결">SETTINGS</button>' in page


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
    # UI_SPEC 6절: 이름표 11px 이상(영상 길이, 진행 단계 이름 포함, 좁은 화면 포함)
    css = make_client(key=None).get("/static/css/style.css").text
    sizes = [float(x) for x in re.findall(r"font-size:\s*([\d.]+)px", css)]
    assert sizes and min(sizes) >= 11
    for selector in (".duration {", ".job-steps li {"):
        rule = css.split(selector, 1)[1].split("}", 1)[0]
        assert "font-size: 11px" in rule


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
    # 분석(5단계)은 그대로 꺼져 있다. 초안 글 상자는 6단계에서 켰다(아래 테스트)
    off_blocks = analyze.split('<div class="is-off">')[1:]
    assert len(off_blocks) == 1
    assert "CONTEXT REPORT · 5단계에서 연결" in off_blocks[0]
    assert "자막 출처" not in off_blocks[0].split("</dl>", 1)[0]


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
    # 버전은 단계가 끝날 때마다 하나씩 올린다(실행 순서 3 → P → 6 → 4: 0.3.0 → 0.4.0 → 0.5.0)
    assert "V 0.5.0 — LOCAL · 4단계" in page
    assert "STAGE 4" in page


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
    # 5단계 것은 꺼 둔 채로 "5단계에서 연결"
    button = '<button type="button" class="line-btn is-off" disabled>'
    assert button + "다른 초안 생성 ↗ · 5단계에서 연결</button>" in draft
    assert "영상의 구체적 장면은 실제 자막 등 검증 가능한 근거가 있을 때만 반영합니다." in analyze


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
