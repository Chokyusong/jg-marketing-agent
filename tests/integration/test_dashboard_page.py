"""화면 골격(UI_SPEC 4판, R1 프로그램형 화면): TestClient로 HTML 구조와 정적 파일을 확인한다.

3판(에디토리얼 목업) 구조를 확인하던 테스트를 R1 구조로 옮겼다. 확인하는 기능은 같다:
세 칸과 진행 단계, 검색·거르기·링크 불러오기, 자막 붙여넣기, 초안 글 상자와 규칙 검사, 분석 줄,
오늘 숫자·설정·기록, 게시 작업 상자, 상태 줄, 쇼츠 빼기, 연애 고민 없음 안내, 다음 행동 하나만 강조,
한 화면 배치, 글자 크기, 해시태그 흐리게. 3판의 겹침 패널(설정·기록 전체)은 화면으로 옮겼다.
"""

import re

import pytest

JS_FILES = ["app.js", "api.js", "state.js", "format.js", "discover.js", "analysis.js", "flow.js",
            "topbar.js", "context.js", "draft.js", "report.js", "ops.js", "job.js", "sandbox.js",
            "next.js", "screens.js", "layout.js", "settings.js", "profiles.js", "setup.js"]
# 화면에 쓰지 않는 개발 용어(UI_SPEC 4판 1절 5)
FORBIDDEN = ("sandbox", "assist", "target", "config", "env", "단위", "playwright", "headless")


@pytest.fixture
def page(make_client):
    res = make_client(key=None).get("/")
    assert res.status_code == 200
    return res.text


def _section(page: str, start: str, end: str) -> str:
    return page.split(start, 1)[1].split(end, 1)[0]


def test_layout_parts_exist(page):
    assert "JG Marketing" in page  # 1단계 테스트와 같은 확인(창 제목)
    # 왼쪽 줄 · 위 줄 · 화면 내용 · 아래 줄
    assert '<nav class="rail" id="nav" aria-label="화면">' in page
    assert '<div class="logo" aria-hidden="true">JG</div>' in page
    screens = (("work", "작업"), ("records", "기록"), ("profiles", "프로필"), ("settings", "설정"))
    for key, name in screens:
        btn = _section(page, f'id="nav-{key}" data-screen="{key}"', "</button>")
        assert "<svg" in btn and f"<span>{name}</span>" in btn  # 인라인 아이콘 + 한글 이름
        assert f'id="screen-{key}"' in page
    assert '<header class="topbar">' in page and 'id="screen-title"' in page
    steps = re.findall(r'<li class="step[^"]*" data-step="(\d)">([^<]+)</li>', page)
    assert steps == [("1", "① 영상 불러오기"), ("2", "② 영상 선택"), ("3", "③ 댓글 달기")]
    assert 'id="next-hint"' in page and "다음: [영상 불러오기]를 누르세요" in page
    assert '<footer class="statusbar" aria-label="상태">' in page
    for col, title in (("col-discover", "① 영상 불러오기"), ("col-analyze", "② 영상 선택"),
                       ("col-execute", "③ 댓글 달기")):
        assert f'id="{col}"' in page
        assert f'<h2 id="{col}-title" tabindex="-1">{title}</h2>' in page
    assert 'id="activity"' in page
    # 작업 화면 말고는 처음에 숨겨 둔다
    for key in ("records", "profiles", "settings"):
        assert re.search(rf'id="screen-{key}"[^>]*hidden>', page)


def test_discover_column_is_wired(page):
    assert 'id="tab-keyword"' not in page and 'id="tab-url"' not in page  # 탭 없이 둘 다 보인다
    assert re.search(r'id="q"[^>]*value="연애 고민"', page)  # 입력 없이 바로 누를 수 있다
    assert 'id="search-btn">영상 불러오기<' in page
    assert 'id="period"' in page and 'id="order"' in page and 'id="max-results"' in page
    for order in ("date", "relevance", "viewCount"):
        assert f'<option value="{order}"' in page
    assert '<option value="12" selected>' in page  # config.yaml discover.max_results
    assert 'id="video-list"' in page
    assert 'id="discover-error"' in page and 'role="alert"' in page
    # 「영상 링크로 불러오기」는 눈에 보이게 따로(가점 항목)
    link = _section(page, '<form id="resolve-form"', "</form>")
    assert '<label for="video-url">영상 링크로 불러오기</label>' in link
    assert 'id="resolve-btn">불러오기</button>' in link
    assert "디자인 시연용 가상 데이터" not in page


def test_unconnected_parts_are_off_and_labelled(page):
    for stage in range(3, 10):
        assert f"{stage}단계에서 연결" not in page
    # R4: [뜨기 직전 영상]이 연결됐다(꺼 두지 않고 「곧 연결」도 없다). 초안까지만이라고 알린다
    rising = _section(page, 'id="rising-btn"', "</button>")
    assert "disabled" not in rising and "곧 연결" not in rising
    assert rising.endswith(">뜨기 직전 영상") and "초안까지만" in rising
    assert "곧 연결" not in page
    # R2: 설정 [저장] · [기본값으로]는 연결됐다([저장]은 바꾼 칸이 생길 때까지만 꺼 둔다)
    assert '<button type="button" class="btn" id="settings-save" disabled>저장</button>' in page
    reset = '<button type="button" class="btn btn-text" id="settings-reset">기본값으로</button>'
    assert reset in page
    assert "곧 연결됩니다" not in _section(page, 'id="screen-settings"', "</section>")
    assert "<dialog" not in page  # 3판의 겹침 패널은 화면으로 옮겼다
    assert '<fieldset class="settings" id="exec-settings">' in page  # ③ 설정은 켜져 있다


def test_no_example_numbers(page):
    today = _section(page, '<dl class="today', "</dl>")
    for value in re.findall(r'<dd id="[^"]+">(.*?)</dd>', today, re.S):
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


def test_panels_js_is_gone(make_client):
    # 겹침 패널(panels.js)은 기록·프로필·설정 화면(screens.js)으로 옮겼다
    assert make_client(key=None).get("/static/js/panels.js").status_code == 404


def test_static_css_follows_spec(make_client):
    # UI_SPEC 4판 8절의 색
    css = make_client(key=None).get("/static/css/style.css").text
    for token in ("--bg: #0b0b0c", "--panel: #141416", "--field: #1b1b1e", "--line: #2a2a2e",
                  "--text: #f1efea", "--sub: #a8a59e", "--gold: #d1b990", "--ok: #8fbf8f",
                  "--bad: #e08b7f", "--warn: #e0c27a", "Noto Serif KR"):
        assert token in css, token
    assert "@media (max-width: 1099px)" in css  # 1100px 아래: 아이콘만 · 세 칸은 탭
    assert "@import" not in css and "url(http" not in css  # 외부 글꼴 없음
    # 명조는 로고와 화면 이름에만
    serif = [line.split("{", 1)[0].strip() for line in css.splitlines() if "var(--serif)" in line]
    assert serif == [".logo", ".topbar h1"]
    # 모서리: 단추 6px, 칸 8px
    assert "border-radius: 6px" in css.split(".btn {", 1)[1].split("}", 1)[0]
    assert "border-radius: 8px" in css.split(".column {", 1)[1].split("}", 1)[0]


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


def test_text_is_at_least_12px(make_client):
    # UI_SPEC 4판 1절 7: 가장 작은 글 12px(영상 길이, 진행 단계 이름, 좁은 화면 포함)
    css = make_client(key=None).get("/static/css/style.css").text
    sizes = [float(x) for x in re.findall(r"font-size:\s*([\d.]+)px", css)]
    assert sizes and min(sizes) >= 12
    for selector in (".duration {", ".job-steps li {", ".run-steps li {"):
        rule = css.split(selector, 1)[1].split("}", 1)[0]
        assert "font-size: 12px" in rule


def test_buttons_and_inputs_are_at_least_36px(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    for selector in (".btn {", ".field, select {", ".col-tab {", ".seg span {"):
        rule = css.split(selector, 1)[1].split("}", 1)[0]
        assert "min-height: 36px" in rule, selector


def test_broken_thumbnail_falls_back_to_empty_box(make_client):
    # 그림을 못 불러오면 img를 떼어 내 빈 자리(.thumb 배경)만 남긴다. ①·② 칸이 같은 함수를 쓴다.
    client = make_client(key=None)
    fmt = client.get("/static/js/format.js").text
    body = fmt.split("export function thumbnail(video) {", 1)[1]
    assert "addEventListener('error', () => img.remove()" in body
    for name in ("discover.js", "analysis.js"):
        js = client.get(f"/static/js/{name}").text
        assert "thumbnail(video)" in js
        assert "el('img'" not in js  # 썸네일 그림은 thumbnail()만 만든다


# ---------------------------------------------------------------- 화면 글: 쉬운 한국어만


def _visible_text(page: str) -> list[str]:
    """템플릿을 그린 HTML에서 사람이 보는 글: 글자 마디와 title·placeholder·aria-label 값."""
    body = page.split("<body>", 1)[1]
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)
    attrs = re.findall(r'(?:title|placeholder|aria-label)="([^"]*)"', body)
    text = re.sub(r"<[^>]+>", "\n", body)
    return [t.strip() for t in text.splitlines() + attrs if t.strip()]


def _js_text_literals(source: str) -> list[str]:
    """JS 소스의 문자열 글자 부분(주석과 템플릿 문자열의 ${…} 식은 뺀다).

    한글이 든 것만 돌려준다.
    """
    out: list[str] = []
    stack: list[list] = [["code", 0]]  # 맨 위가 지금 읽는 곳: ["code", 중괄호 깊이] | ["tpl", 글자]
    i, n = 0, len(source)
    while i < n:
        top, c = stack[-1], source[i]
        if top[0] == "tpl":
            if c == "\\":
                top[1] += source[i:i + 2]
                i += 2
            elif c == "`":
                out.append(stack.pop()[1])
                i += 1
            elif source.startswith("${", i):
                stack.append(["code", 1])
                i += 2
            else:
                top[1] += c
                i += 1
        elif source.startswith("//", i):
            end = source.find(chr(10), i)
            i = n if end < 0 else end
        elif source.startswith("/*", i):
            i = source.find("*/", i) + 2
        elif c in "'\"":
            j, buf = i + 1, []
            while j < n and source[j] != c:
                buf.append(source[j:j + 2] if source[j] == "\\" else source[j])
                j += 2 if source[j] == "\\" else 1
            out.append("".join(buf))
            i = j + 1
        elif c == "`":
            stack.append(["tpl", ""])
            i += 1
        elif c == "{":
            top[1] += 1
            i += 1
        elif c == "}":
            top[1] -= 1
            if top[1] == 0 and len(stack) > 1:
                stack.pop()  # ${ … } 끝: 템플릿 글자로 돌아간다
            i += 1
        else:
            i += 1
    return [t for t in out if re.search(r"[가-힣]", t)]


def test_js_text_literal_reader_skips_code_inside_templates():
    src = "const a = `${targetName(job.target)} · 실패`; // sandbox 주석\nconst b = '연습 페이지';"
    assert _js_text_literals(src) == [" · 실패", "연습 페이지"]


def test_screen_text_has_no_dev_words_or_english_labels(page, make_client):
    visible = _visible_text(page)
    joined = "\n".join(visible).lower()
    for word in FORBIDDEN:
        assert word not in joined, word
    for gone in ("INTELLIGENT CONTENT WORKFLOW", "01 / 03", "02 / 03", "03 / 03", "↗"):
        assert gone not in page
    # 영문 대문자 이름표 없음(JG·AI·API·PC는 이름이라 둔다)
    upper = {w for t in visible for w in re.findall(r"\b[A-Z]{2,}\b", t)}
    assert upper <= {"JG", "AI", "API", "PC"}, upper
    client = make_client(key=None)
    for name in JS_FILES:
        if name == "sandbox.js":  # 연습 페이지(유튜브 흉내 화면) 전용
            continue
        literals = _js_text_literals(client.get(f"/static/js/{name}").text)
        for text in literals:
            low = text.lower()
            for word in FORBIDDEN:
                assert word not in low, (name, word, text)
            assert "↗" not in text and "V1~V12" not in text, (name, text)


# ---------------------------------------------------------------- 3단계: ② 자막·붙여넣기


def test_context_rows_are_on(page):
    analyze = _section(page, 'id="col-analyze"', 'id="col-execute"')
    box = _section(analyze, 'id="context-box"', 'id="draft-box"')
    assert 'class="is-off"' not in box
    assert '<dt>자막</dt><dd id="ctx-transcript">' in box
    assert '<dt>인기 댓글</dt><dd id="ctx-comments">' in box
    assert 'id="context-error"' in box and 'role="alert"' in box


def test_transcript_paste_box(page):
    box = _section(page, 'id="transcript-paste"', "</details>")
    assert page.count('<details class="paste" id="transcript-paste">') == 1  # 접어 둔 채(open 없음)
    assert "<summary>자막 직접 넣기" in box
    # R4: 자동으로 못 읽었을 때만 보이는 안내(처음에는 숨김)
    assert 'id="transcript-paste-hint" hidden> · 자동으로 못 읽었을 때 여기에 붙여 넣으세요' in box
    assert "유튜브 영상 아래 「스크립트 표시」에서 복사해 붙여 넣으세요." in box
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
    # 2026-11-18: 자막이 없으면 무엇만 읽었는지 + 초안이 밋밋할 수 있다
    # (예전 「자막 없음 · 제목과 설명으로 대신」)
    for text in ("붙여 넣은 자막 ", "자막이 없어 제목·설명·댓글만 읽었습니다",
                 "초안이 밋밋할 수 있어요", "인기 댓글 ", "댓글이 막힌 영상", "transcript:saved"):
        assert text in js
    assert "api.buildContext(videoId)" in js
    assert "api.saveTranscript(videoId, text)" in js
    assert "initContext" in client.get("/static/js/app.js").text


def test_version_shows_in_status_bar(page):
    # 버전은 단계가 끝날 때마다 하나씩 올린다. 아래 줄 맨 오른쪽
    bar = _section(page, '<footer class="statusbar"', "</footer>")
    assert '<span class="version">JG 마케팅 에이전트 · V 0.9.0</span>' in bar


# ---------------------------------------------------------------- 6단계: ② 댓글 초안·규칙 검사


def test_draft_box_is_on(page):
    analyze = _section(page, 'id="col-analyze"', 'id="col-execute"')
    draft = _section(analyze, 'id="draft-box"', "</section>")
    assert 'data-min="40"' in page and 'data-max="120"' in page  # config.yaml comment
    assert '<label for="draft-text">댓글 초안</label>' in draft
    assert 'id="draft-count">0 / 120자</span>' in draft
    assert '<textarea class="draft-input" id="draft-text"' in draft
    assert 'id="draft-mirror" aria-hidden="true"' in draft  # 표기 금색으로 칠하는 거울
    assert 'id="draft-tag">검토 필요</span>' in draft
    assert 'id="draft-checks" aria-live="polite"' in draft
    # [다른 댓글 만들기](초안이 생기기 전에는 눌리지 않는다). 따로 승인하는 단추는 없다
    assert 'id="another-btn" disabled>다른 댓글 만들기</button>' in draft
    assert 'id="approve-btn"' not in page


def test_disclosure_toggle_starts_from_the_setting(page, make_client):
    # 「광고 표기 붙이기」(R3): 모든 영상에서 켜고 끌 수 있다. 처음 상태는 comment.disclose_default.
    # 영상을 고르기 전에는(초안 칸이 잠겨 있을 때) 같이 잠겨 있다
    draft = _section(page, 'id="draft-box"', 'class="draft-edit"')
    assert 'id="disclose-toggle"' in draft and "광고 표기 붙이기" in draft
    assert '<input type="checkbox" id="disclose" checked disabled />' in draft
    assert 'data-disclose-default="true"' in page
    assert "끄면 광고 표기 없이 댓글을 답니다" in draft  # title로 알린다
    assert "내 채널" not in draft
    off = make_client(key=None, overrides={"comment": {"disclose_default": False}})
    page_off = off.get("/").text
    assert '<input type="checkbox" id="disclose" disabled />' in page_off
    assert 'data-disclose-default="false"' in page_off


def test_draft_js_checks_after_pause_and_folds_passed_items(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    assert "request('/api/validate', { method: 'POST'" in api
    assert "video_id: videoId, text" in api
    js = client.get("/static/js/draft.js").text
    assert "const DEBOUNCE_MS = 400;" in js  # 입력이 0.4초 멈추면 검사
    assert "api.validate(videoId, text, discloseOn())" in js
    assert "api.setDisclosure(" in js  # 켬/끔은 저장한 초안을 모델 없이 고친다
    for text in ("'검사 통과'", "'검토 필요'", "'승인됨'", "개 중 ", "개 통과", "개 모두 통과",
                 "checks-fail", "class: 'disclosure'", "normalize('NFC').trim()"):
        assert text in js
    # 통과 항목은 접어 두고(details) 실패만 펼친다
    assert "el('details'" in js and "failed.map(" in js
    assert "initDraft" in client.get("/static/js/app.js").text
    flow = client.get("/static/js/flow.js").text
    assert "v.result.passed" in flow  # 초안이 통과하면 진행 단계 ③


def test_draft_styles(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    assert ".gold, .disclosure { color: var(--gold); }" in css  # 거울의 표기를 금색으로
    assert ".draft-input {" in css and "color: transparent" in css.split(".draft-input {", 1)[1]
    assert ".checks-fail li {" in css and ".tag.is-ok" in css


# ---------------------------------------------------------------- 5단계: ② 자동 분석·초안


def test_report_box_runs_by_itself_with_three_steps(page):
    analyze = _section(page, 'id="col-analyze"', 'id="col-execute"')
    report = _section(analyze, 'id="report-box"', 'id="context-box"')
    # 영상을 고르면 자동으로 돈다: [분석하고 초안 만들기] 단추가 없다. [다시 해 보기]는 오류 안에만
    assert "분석하고 초안 만들기" not in page
    run_error = _section(report, 'id="run-error"', "</div>")
    assert 'id="run-btn" disabled>다시 해 보기</button>' in run_error
    phases = re.findall(r'<li data-phase="(\w+)">([^<]+)</li>', report)
    assert phases == [
        ("context", "영상 자료 읽는 중"), ("analysis", "고민 정리 중"), ("draft", "댓글 쓰는 중"),
        ("review", "다듬는 중")]  # 2026-11-18 AI 검수 한 번
    assert "처음에는 1분쯤 걸릴 수 있습니다" in report  # 긴 작업 안내
    assert 'id="run-error" role="alert" hidden' in report
    assert '<p class="label">영상 속 고민 한 줄</p>' in report and 'id="an-concern"' in report
    assert 'id="an-evidence"' in report  # 근거 문장
    terms = (("주제", "an-topic"), ("분위기", "an-tone"), ("보는 사람이 바라는 것", "an-needs"))
    for dt, dd in terms:
        assert f'<dt>{dt}</dt><dd id="{dd}">' in report
    # C1: 핵심 말 줄(주제 위)
    assert '<dt>핵심 말</dt><dd id="an-keys">' in report
    assert report.index('id="an-keys"') < report.index('id="an-topic"')
    assert 'id="draft-tone"' in page  # 말투 분류(본문에는 넣지 않는다)


def test_post_button_is_one_click(page):
    execute = _section(page, 'id="col-execute"', 'id="activity"')
    # [댓글 달기] 하나로 저장 → 승인 → 게시 작업 시작(켜는 조건은 job.js의 startBlocker)
    primary = '<button type="button" class="btn btn-big" id="job-primary" disabled>'
    assert primary + "댓글 달기</button>" in execute
    assert 'id="job-why"' in execute  # 못 누를 때 이유


def test_report_js_runs_steps_in_order_when_video_is_picked(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    for snippet in ("`/api/analysis/${encodeURIComponent(videoId)}`, { method: 'POST' }",
                    "request('/api/drafts', { method: 'POST'", "`/api/drafts?video_id=",
                    "method: 'PATCH'", "`/api/drafts/${id}/approve`", "this.failures = failures"):
        assert snippet in api, snippet
    js = client.get("/static/js/report.js").text
    # 영상을 고르면: 저장된 초안이 있으면 그것(모델을 부르지 않는다), 없으면 자동으로 만든다
    select_block = js.split("if (state.selectedId !== lastSelected) {", 1)[1].split("return;", 1)[0]
    assert "runToken += 1" in select_block and "pick(state.selectedId)" in select_block
    pick = js.split("async function pick(videoId) {", 1)[1].split("\n}\n", 1)[0]
    order = [pick.index(s) for s in ("api.listDrafts(videoId)", "loadDraft(stored)", "run(videoId")]
    assert order == sorted(order)
    assert js.index("waitForContext(videoId)") < js.index("api.analyze(videoId)") < js.index(
        "api.createDraft(videoId")
    # 늦게 온 결과는 버린다(차례 번호), 타이머도 그 차례 것만 멈춘다
    assert "const live = () => token === runToken && mine(videoId);" in js
    assert "if (token === runToken) stopTicker();" in js
    for text in ("처음에는 1분쯤 걸릴 수 있습니다", "번째 초안이 규칙 검사를 통과했습니다",
                 "another: true", "api.updateDraft(draft.id, text)",
                 "api.approveDraft(current.id)", "외 ", "setAttribute('title'",
                 "export async function ensureApproved()", "앞서 만든 초안"):
        assert text in js, text
    draft = client.get("/static/js/draft.js").text
    assert "export function loadDraft(draft)" in draft and "말투 · " in draft
    assert "initReport" in client.get("/static/js/app.js").text
    flow = client.get("/static/js/flow.js").text
    assert "return 3;" in flow and "return 2;" in flow and "return 1;" in flow


def test_report_lines_are_clipped_to_one_line(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    rule = css.split(".analysis dd {", 1)[1].split("}", 1)[0]
    for token in ("white-space: nowrap", "overflow: hidden", "text-overflow: ellipsis"):
        assert token in rule
    assert ".run-steps li.is-current" in css


# ---------------------------------------------------------------- 7단계: 오늘 숫자·설정·기록


def test_today_stats_are_on_and_start_empty(page):
    records = _section(page, 'id="screen-records"', "</section>")
    today = _section(records, '<dl class="today"', "</dl>")
    for dd_id, label in (("stat-videos", "오늘 게시"), ("stat-drafts", "만든 댓글"),
                         ("stat-posted", "게시 완료"), ("stat-success", "성공률")):
        assert f'<dt>{label}</dt><dd id="{dd_id}">–</dd>' in today  # 값은 화면이 API로 채운다
    assert 'id="today-note"' in page
    assert 'id="today-count">–/10</span>' in page  # 아래 줄 오늘 게시 n/상한


def test_execute_settings_are_on(page):
    execute = _section(page, 'id="col-execute"', 'id="activity"')
    settings = _section(execute, '<div class="exec-settings"', '<div class="jobbox"')
    assert 'class="is-off"' not in settings
    assert 'data-limit="10"' in settings
    assert '<option value="" selected>자동 배정</option>' in settings
    for name in ("유튜브1", "유튜브2", "유튜브3"):
        assert f'<option value="{name}">{name}</option>' in settings
    # 연습 모드 스위치(R3): 처음 값은 기본 게시 방식(config.yaml browser.default_target = 실제 게시)
    # → 꺼져 있다
    assert re.search(r'id="practice-mode" role="switch"[^>]*>', settings)
    assert not re.search(r'id="practice-mode" role="switch"[^>]*checked', settings)
    assert '<span class="label" id="practice-label">연습 모드</span>' in settings
    assert "꺼짐 · 실제 유튜브에 답니다" in settings
    assert 'data-confirm="false"' in execute  # 게시 직전 확인(기본 끔)
    # 하루 상한은 설정값 이하로만 고른다
    assert re.findall(r'<option value="(\d+)"[^>]*>\d+개까지', settings) == ["10", "5", "3", "1"]
    assert '<option value="10" selected>10개까지</option>' in settings
    assert '<ol class="job-steps" id="job-steps" aria-label="진행 상태: ' in execute


def test_daily_limit_options_follow_config(make_client):
    page = make_client(key=None, overrides={"limits": {"daily_max_comments": 3},
                                            "browser": {"default_target": "assist"}}).get("/").text
    settings = _section(page, '<div class="exec-settings"', '<div class="jobbox"')
    assert re.findall(r'<option value="(\d+)"[^>]*>\d+개까지', settings) == ["3", "1"]
    assert not re.search(r'id="practice-mode"[^>]*checked', settings)  # 실제 유튜브 → 연습 모드 끔
    assert "꺼짐 · 실제 유튜브" in settings


def test_records_table_is_on(page):
    history = _section(page, 'id="activity"', "</section>")
    assert 'id="records-meta">최근 4줄<' in history
    heads = re.findall(r"<th>([^<]+)</th>", history)
    assert heads == ["시간", "영상", "프로필", "댓글", "결과"]
    assert '<tbody id="records-body">' in history
    assert "아직 기록이 없습니다." in history
    assert '<col class="c-comment" />' in history
    assert 'id="records-all">기록 전체 보기</button>' in history


def test_ops_js_wires_the_three_apis(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    for snippet in ("`/api/profiles?target=", "`/api/records?limit=", "`/api/stats/today?"):
        assert snippet in api, snippet
    js = client.get("/static/js/ops.js").text
    # 2026-11-17: 숫자는 실제 게시 기준(youtube), 연습(sandbox)은 따로 받아 「연습 n」
    for text in ("api.todayStats('youtube', ops.dailyLimit)",
                 "api.todayStats('sandbox', ops.dailyLimit)", "api.records(RECENT_FETCH)",
                 "const RECENT_ROWS = 4;", "r.action === 'post'", "timeZone: 'Asia/Seoul'", "'–'",
                 "setInterval(refreshOps", "export async function refreshOps()",
                 "practice.checked ? 'sandbox' : 'youtube'",
                 "practice.checked = practice.defaultChecked;"):
        assert text in js, text
    assert "initOps" in client.get("/static/js/app.js").text
    report = client.get("/static/js/report.js").text
    assert report.count("refreshOps();") == 2  # 분석·초안이 끝날 때, 승인이 끝날 때
    discover = client.get("/static/js/discover.js").text
    assert "댓글 달았음" in discover and "video.commented" in discover


def test_records_and_commented_styles(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    assert ".commented {" in css and "var(--ok)" in css.split(".commented {", 1)[1].split("}", 1)[0]
    assert "table-layout: fixed" in css
    for tone in (".st.is-ok b", ".st.is-bad b"):
        assert tone in css


# ---------------------------------------------------------------- 8단계: ③ 작업 상자 · 상태 줄


def test_job_box_has_three_steps_and_only_needed_buttons(page):
    box = _section(page, 'id="job-box"', '<section class="history"')
    steps = re.findall(r'<li data-phase="(\d)">([^<]+)</li>', box)
    # 2026-11-17(PDF 대조): 과제 문구 그대로 「프로필 여는 중 → 입력 중 → 게시 완료」
    assert steps == [("1", "프로필 여는 중"), ("2", "입력 중"), ("3", "게시 완료")]
    assert 'aria-label="진행 상태: 프로필 여는 중 → 입력 중 → 게시 완료"' in box
    # [댓글 보기]는 「게시 완료」 제목 옆
    head = _section(box, 'class="job-head"', "</a></div>")
    assert 'id="exec-title"' in head and 'id="job-view"' in head
    # 상태에 따라 필요한 것만 보인다: 작은 단추 줄과 실패 이유는 처음에 숨김
    assert 'class="job-actions" id="job-actions" hidden' in box
    assert 'id="job-cancel" hidden>그만두기</button>' in box
    # R3: 사람이 직접 게시하던 방식의 단추([댓글 복사]·[게시 안 함])는 없다
    assert 'id="job-copy"' not in box and 'id="job-not-posted"' not in box
    view = 'id="job-view" href="#" target="_blank" rel="noopener noreferrer" hidden>댓글 보기'
    assert view in box
    assert 'id="job-shot"' in box and "화면 캡처 보기" in box
    assert 'id="job-error" role="alert" hidden' in box
    assert 'id="job-status"' in box


def test_status_bar_is_on(page):
    bar = _section(page, '<footer class="statusbar"', "</footer>")
    items = (("ai", "AI 모델", "settings"), ("youtube", "유튜브 연결", "settings"),
             ("browser", "프로필", "profiles"))
    for name, label, screen in items:
        item = _section(bar, f'id="status-{name}-item"', "</button>")
        assert f'data-screen="{screen}"' in item  # 누르면 해당 화면으로
        assert f'id="status-{name}-dot"' in item
        assert f'<span class="stat-name">{label}</span>' in item
        assert f'id="status-{name}">확인 중<' in item
    assert 'id="today-item" data-screen="records"' in bar


def test_job_js_wires_the_job_apis(make_client):
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    for snippet in ("request('/api/jobs', {", "`/api/jobs/${encodeURIComponent(id)}`",
                    "/approve`", "/cancel`"):
        assert snippet in api, snippet
    js = client.get("/static/js/job.js").text
    for text in ("const POLL_MS = 500;", "api.startJob(", "api.approveJob(job.id)",
                 "api.cancelJob(job.id)",
                 "refreshOps();", "commented: { ...(v.commented || {}), [job.target]: true }",
                 "연습 모드 · 실제 유튜브가 아니라", "video.commented[target]",
                 "ops.stats.remaining <= 0", "active_job_id", "'게시'",
                 "'다시 시도'", "프로필 여는 중", "입력 중", "게시 완료"):
        assert text in js, text
    # R3: 사람이 직접 게시하던 방식(댓글 복사·「게시했어요」)은 화면에서 뺐다
    for gone in ("api.confirmJob(", "navigator.clipboard", "게시했어요"):
        assert gone not in js, gone
    # [댓글 달기] 한 번: 저장·승인(ensureApproved) 다음에 시작
    start = js.split("function start() {", 1)[1].split("\n}\n", 1)[0]
    assert start.index("await ensureApproved()") < start.index("api.startJob(")
    assert "innerHTML" not in js
    assert "initJob" in client.get("/static/js/app.js").text
    topbar = client.get("/static/js/topbar.js").text
    assert "export function browserStatusText" in topbar
    assert "paintItem('browser', browser)" in topbar


def test_job_box_styles(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    for rule in (".job-steps li.is-current", ".job-steps li.is-done", ".job-steps li.is-failed",
                 ".job-actions {", ".job-error {"):
        assert rule in css, rule


def test_hidden_job_buttons_stay_hidden(make_client):
    """작은 단추의 display 규칙이 hidden을 이기면 안 된다(상태마다 필요한 단추만 보인다)."""
    css = make_client(key=None).get("/static/css/style.css").text
    assert "[hidden] { display: none !important; }" in css


# ---------------------------------------------------------------- 실제 데이터 보정


def test_discover_has_exclude_shorts_checked_by_default(page, make_client):
    # ① 거르기 줄의 「쇼츠 빼기」 체크(config.yaml discover.exclude_shorts = 기본 켬)
    assert re.search(r'id="exclude-shorts"[^>]*checked', page)
    assert "쇼츠 빼기" in page
    client = make_client(key=None)
    api = client.get("/static/js/api.js").text
    assert "params.set('exclude_shorts', String(excludeShorts))" in api
    discover = client.get("/static/js/discover.js").text
    assert "excludeShorts: $('exclude-shorts')" in discover
    assert "`쇼츠 ${state.meta.shortsExcluded}개 뺌`" in discover  # 결과 줄
    filters = _section(page, '<div class="filters">', "</div>")
    assert 'id="exclude-shorts"' in filters  # 같은 줄(높이가 늘지 않게)


def test_exclude_shorts_always_starts_from_config_default(page, make_client):
    # 창을 새로 고쳐도 브라우저가 앞서 바꾼 체크를 되살리지 않게 폼 자동 복원을 끄고,
    # 시작할 때 HTML의 처음 값으로 되돌린다(2026-11-17)
    assert '<form id="search-form" autocomplete="off">' in page
    assert re.search(r'id="exclude-shorts"[^>]*autocomplete="off"', page)
    discover = make_client(key=None).get("/static/js/discover.js").text
    init = discover.split("export function initDiscover() {", 1)[1]
    assert "shorts.checked = shorts.defaultChecked;" in init
    assert init.index("shorts.defaultChecked") < init.index("setupList();")


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
    assert "이 영상에서는 연애 고민을 찾지 못했습니다" in js  # 고민 한 줄 자리
    # 오류 문구는 서버 문구를 그대로 띄운다(run-error)
    assert "$('run-error-msg').textContent = err.message" in js
    # 자막을 넣고 [저장]하면 초안을 다시 만든다
    assert "document.addEventListener('transcript:saved'" in js
    page = client.get("/").text
    assert 'id="transcript-paste"' in page and 'id="run-error"' in page


# ---------------------------------------------------------------- R1: 화면 네 개


def test_screens_replace_overlay_panels(page):
    records = _section(page, 'id="screen-records"', "<!-- 프로필 화면 -->")
    assert 'role="radiogroup" aria-label="거르기"' in records
    # 2026-11-17(PDF 대조): 처음 거르기는 게시(성공·실패). 분석·초안·승인 줄은 「모든 활동」에서
    for value, label in (("post", "게시"), ("failure", "실패"), ("all", "모든 활동")):
        assert f'name="records-filter" value="{value}"' in records
        assert f"<span>{label}</span>" in records
    assert 'name="records-filter" value="post" checked' in records
    assert records.index('value="post"') < records.index('value="failure"') < records.index(
        'value="all"')
    assert 'id="records-all-body"' in records
    heads = re.findall(r"<th>([^<]+)</th>", records)
    assert heads == ["시간", "영상", "프로필", "댓글", "결과"]
    profiles = _section(page, 'id="screen-profiles"', "<!-- 설정 화면")
    assert 'class="screen-note"' in profiles and "꼭 필요한 것은 유튜브1 하나입니다" in profiles
    assert 'id="profiles-body"' in profiles
    settings = _section(page, 'id="screen-settings"', "</section>")
    assert 'id="settings-body"' in settings and 'id="settings-save"' in settings


def test_screens_js_loads_on_show_and_keeps_keys_hidden(make_client):
    client = make_client(key=None)
    js = client.get("/static/js/screens.js").text
    for snippet in ("document.addEventListener('screen:show'", "api.records(ALL_ROWS)",
                    "has_screenshot", "/screenshot`", "화면 캡처", "유튜브에서 보기",
                    "showScreen('records'"):
        assert snippet in js, snippet
    # R2: 프로필 화면(profiles.js) — 로그인 단추 세 개가 API를 부른다
    profiles = client.get("/static/js/profiles.js").text
    for snippet in ("document.addEventListener('screen:show'", "api.profiles('sandbox')",
                    "api.profiles('youtube')", "로그인하기", "로그인 확인", "유튜브 열기",
                    "api.profileLogin", "api.profileCheck", "api.profileOpen",
                    "로그인을 마치고 크롬 창을 닫은 다음 [로그인 확인]을 누르세요"):
        assert snippet in profiles, snippet
    assert "곧 연결" not in profiles
    # R2: 설정 화면(settings.js) — 다섯 묶음, 저장 · 기본값으로 · 키 저장 · 연결 확인
    js = client.get("/static/js/settings.js").text
    for snippet in ("'유튜브 연결'", "'AI 모델'", "'댓글 규칙'", "'게시'", "'영상 찾기'",
                    "api.saveSettings(changes)", "api.resetSettings()", "api.saveKey(key)",
                    "api.deleteKey()", "api.testKey()", "api.llmModels()", "api.screens()",
                    "type: 'password'", "곧 적용", "applyWorkDefaults"):
        assert snippet in js, snippet
    # [미리 불러오기]는 단추를 눌렀을 때만 부른다(화면을 연다고 부르지 않는다)
    assert js.count("api.warmup()") == 1
    assert "$('warmup-btn').addEventListener('click', warmup);" in js
    api = client.get("/static/js/api.js").text
    assert "settings: () => request('/api/settings')" in api
    assert "warmup: () => request('/api/llm/warmup', { method: 'POST' })" in api
    # 화면에 키 값을 그리지 않는다(있다/없다만). 넣은 칸은 보내자마자 비운다
    assert "key_configured" in js and "api_key" not in js
    assert "input.value = ''; // 보낸 값은 화면에 남기지 않는다" in js
    setup = client.get("/static/js/setup.js").text
    for snippet in ("focusSetting('set-key')", "focusSetting('set-model')", "focusProfile(",
                    "has-setup", "setup-close"):
        assert snippet in setup, snippet
    topbar = client.get("/static/js/topbar.js").text
    for snippet in ("export function showScreen(", "aria-current', 'page'",
                    "dispatchEvent(new CustomEvent('screen:show'",
                    "export function showColumn(", "nav-profiles-dot", "nav-settings-dot"):
        assert snippet in topbar, snippet


def test_next_action_highlights_one_thing_in_order(make_client):
    client = make_client(key=None)
    js = client.get("/static/js/next.js").text
    order = ["'search-btn'", "'video-list'", "'job-primary'", "'draft-edit'"]
    for snippet in order + ["'transcript-paste'", "'transcript-save'", "'run-btn'",
                            "classList.add('is-next')", "WAIT_HINT", "next-hint", "[게시]"]:
        assert snippet in js, snippet
    # 금색은 [영상 불러오기] → 고르기 → [댓글 달기]
    assert "'approve-btn'" not in js and "'resolve-btn'" not in js
    assert "처음에는 1분쯤 걸릴 수 있습니다" in js  # 오래 걸리는 일에는 예상 시간
    app = client.get("/static/js/app.js").text
    assert app.rstrip().splitlines()[-1].startswith("initNext();")  # 다른 칸이 다 그린 뒤
    css = client.get("/static/css/style.css").text
    assert ".btn.is-next {" in css
    assert "color: #000" in css.split(".btn.is-next {", 1)[1].split("}", 1)[0]


def test_one_screen_without_page_scroll(make_client):
    # 페이지는 스크롤하지 않는다. 칸 머리는 고정, 칸 몸통(.col-body)만 스크롤,
    # ①은 영상 목록만 스크롤
    client = make_client(key=None)
    css = client.get("/static/css/style.css").text
    for token in ("html, body { height: 100%; margin: 0; overflow: hidden; }",
                  "grid-template-rows: var(--top) minmax(0, 1fr) var(--bottom);",
                  "grid-template-columns: minmax(0, 30fr) minmax(0, 38fr) minmax(0, 32fr);",
                  ".colhead { flex: none;",
                  "#col-discover .col-body { overflow: hidden; }",
                  ".video-list { position: relative; flex: 1 1 auto; min-height: 0; "
                  "overflow-y: auto;"):
        assert token in css, token
    col_body = css.split(".col-body {", 1)[1].split("}", 1)[0]
    assert "min-height: 0" in col_body and "overflow-y: auto" in col_body
    assert "--col-max" not in css and "is-capped" not in css
    narrow = css.split("@media (max-width: 1099px) {", 1)[1]
    assert '.screen-work[data-col="1"] .column:not([data-col="1"])' in narrow  # 좁은 창: 칸 하나씩
    assert ".col-tabs { display: flex;" in narrow
    page = client.get("/").text
    for col in ("col-discover", "col-analyze", "col-execute"):
        # 칸 머리(colhead)는 몸통(.col-body) 밖, 바로 앞에 있다
        head = _section(page, f'id="{col}"', '<div class="col-body">')
        assert head.count('<div class="colhead">') == 1 and "</h2>" in head
    layout = client.get("/static/js/layout.js").text
    assert "keepInList" in layout


def test_body_and_list_text_sizes(make_client):
    css = make_client(key=None).get("/static/css/style.css").text

    def rule(selector, text=css):
        return text.split(selector, 1)[1].split("}", 1)[0]

    assert "15px" in rule(chr(10) + "body {")  # 본문 15px
    assert "font-size: 14px" in rule(".video-title { display")
    assert "font-size: 13px" in rule(".caption, .empty-sm {")  # 보조 글 13px
    assert "font-size: 12px" in rule(".video-meta {")


def test_title_hashtags_are_dimmed_but_title_text_is_unchanged(make_client):
    client = make_client(key=None)
    fmt = client.get("/static/js/format.js").text
    assert "export function splitTitleTags(title)" in fmt and "export function titleNode(" in fmt
    assert "class: 'title-tags'" in fmt
    # 제목이 태그뿐이면 나누지 않는다
    assert "!text.slice(0, found.index).trim()" in fmt
    for name in ("discover.js", "analysis.js"):
        js = client.get(f"/static/js/{name}").text
        assert "titleNode(video.title)" in js, name
    discover = client.get("/static/js/discover.js").text
    assert "title: video.title }" in discover  # 원문 전체는 title 속성에
    css = client.get("/static/css/style.css").text
    assert ".title-tags { color: var(--dim);" in css


def test_upload_date_is_shown_as_date(make_client):
    client = make_client(key=None)
    fmt = client.get("/static/js/format.js").text
    assert "export function formatDay(iso" in fmt and "timeZone: 'Asia/Seoul'" in fmt
    discover = client.get("/static/js/discover.js").text
    assert "formatDay(video.published_at)" in discover
    assert "formatAgo(video.published_at)" in discover


def test_empty_loading_and_error_texts_name_the_next_step(make_client):
    client = make_client(key=None)
    discover = client.get("/static/js/discover.js").text
    for text in ("보통 1~2초 걸립니다", "[영상 불러오기]를 다시 눌러 보세요", "[영상 불러오기]",
                 "영상을 하나 고르세요", "영상 주소를 넣어 주세요."):
        assert text in discover, text
    page = client.get("/").text
    assert "아직 기록이 없습니다." in page
