"""화면 골격(UI_SPEC): TestClient로 HTML 구조와 정적 파일을 확인한다."""

import re

import pytest

JS_FILES = ["app.js", "api.js", "state.js", "format.js", "discover.js", "analysis.js", "sidebar.js"]


@pytest.fixture
def page(make_client):
    res = make_client(key=None).get("/")
    assert res.status_code == 200
    return res.text


def test_layout_parts_exist(page):
    assert 'class="sidebar"' in page
    assert "JG Marketing" in page and "AI Agent" in page
    assert "유튜브 마케팅 AI 에이전트" in page
    assert "TRACK 2 · 제이지그룹 과제" in page
    assert page.count('class="stat ') == 4
    for title in ("오늘 처리한 영상", "생성한 댓글 초안", "게시 완료", "성공률"):
        assert title in page
    for col in ("col-discover", "col-analysis", "col-run"):
        assert f'id="{col}"' in page
    menus = ("대시보드", "영상 탐색", "AI 분석·생성", "실행 관리", "작업 기록", "계정 관리", "설정")
    for menu in menus:
        assert menu in page
    for item in ("AI (Ollama)", "YouTube API", "브라우저"):
        assert item in page


def test_discover_column_is_wired(page):
    assert page.count('role="tablist"') >= 1
    assert 'id="tab-keyword"' in page and 'id="tab-url"' in page
    assert re.search(r'id="q"[^>]*value="연애 고민"', page)  # 입력 없이 바로 누를 수 있다
    assert 'id="search-btn"' in page and "영상 불러오기" in page
    assert 'id="period"' in page and 'id="order"' in page and 'id="max-results"' in page
    assert '<option value="12" selected>' in page  # config.yaml discover.max_results
    assert 'id="video-list"' in page
    assert 'id="discover-error"' in page and 'role="alert"' in page
    assert 'id="resolve-form"' in page


def test_unconnected_parts_are_off_and_labelled(page):
    assert re.search(r'class="panel is-off" id="col-analysis"', page)
    assert re.search(r'class="panel is-off" id="col-run"', page)
    for label in ("3단계에서 연결", "4단계에서 연결", "5단계에서 연결", "7단계에서 연결",
                  "8단계에서 연결"):
        assert label in page
    assert page.count('class="stat is-off"') == 4
    # ③칸의 실행 버튼과 설정은 눌리지 않는다
    assert re.search(r'<fieldset class="settings" disabled>', page)
    assert re.search(r'<button type="button" class="btn btn-big" disabled>', page)


def test_no_example_numbers_in_stats(page):
    stats = page.split('<section class="stats"', 1)[1].split("</section>", 1)[0]
    values = re.findall(r'<p class="stat-value">(.*?)</p>', stats, re.S)
    assert len(values) == 4
    for value in values:
        assert value.strip().startswith("–")
    assert "92 / 120" not in page  # 레퍼런스 이미지의 예시 값


def test_disclosure_and_profiles_from_config(page):
    assert '<span class="disclosure">[광고]</span>' in page
    for name in ("유튜브1", "유튜브2", "유튜브3"):
        assert name in page
    assert "@gmail" not in page  # 계정 이메일을 보이지 않는다


def test_no_external_assets(page):
    for src in re.findall(r'(?:src|href)="([^"#]+)"', page):
        assert src.startswith("/static/"), src


@pytest.mark.parametrize("name", JS_FILES)
def test_static_js_served(make_client, name):
    res = make_client(key=None).get(f"/static/js/{name}")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]


def test_static_css_has_color_variables_and_breakpoints(make_client):
    css = make_client(key=None).get("/static/css/style.css").text
    assert "--accent: #7c5cff" in css
    for bp in ("max-width: 1279px", "max-width: 899px"):
        assert bp in css
    assert "@import" not in css and "url(http" not in css  # 외부 글꼴 없음


def test_js_does_not_use_inner_html(make_client):
    # 영상 제목 등 바깥 글을 innerHTML로 넣지 않는다(textContent만).
    for name in JS_FILES:
        assert "innerHTML" not in make_client(key=None).get(f"/static/js/{name}").text
