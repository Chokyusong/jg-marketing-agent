"""크롬 찾기·프로필 폴더·assist 실행 인자, 그리고 "Playwright가 여는 주소는 sandbox뿐"(8단계).

실제 크롬을 실행하지 않는다. 실행 함수(`subprocess.Popen`)를 가짜로 바꿔 인자만 본다.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

from app.browser import chrome
from app.browser.sandbox_driver import (
    PlaywrightSandboxDriver,
    is_local_url,
    is_sandbox_url,
    require_sandbox_url,
)
from app.config import default_profiles_root, load_settings
from app.errors import AppError

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"


def test_find_chrome_prefers_configured_then_known_places(tmp_path):
    exe = tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    env = {"LOCALAPPDATA": str(tmp_path)}
    assert chrome.find_chrome(environ=env, registry=lambda: None) == exe
    assert chrome.find_chrome(str(exe), environ={}) == exe
    assert chrome.find_chrome(str(tmp_path / "none.exe"), environ=env) is None  # 설정이 틀리면 없음
    assert chrome.find_chrome(environ={}, registry=lambda: None) is None
    assert chrome.find_chrome(environ={}, registry=lambda: exe) == exe


def test_profile_dir_only_accepts_profile_folder_names(tmp_path):
    assert chrome.profile_dir(tmp_path, "profile-2") == tmp_path / "profile-2"
    for bad in ("..", "profile-", "profile-1/../x", "유튜브1", "Default"):
        with pytest.raises(ValueError):
            chrome.profile_dir(tmp_path, bad)
    made = chrome.ensure_profile_dir(tmp_path / "root", "profile-1")
    assert made.is_dir()


def test_profiles_root_is_outside_the_repository():
    root = default_profiles_root({"LOCALAPPDATA": r"C:\Users\x\AppData\Local"})
    assert root == Path(r"C:\Users\x\AppData\Local") / "JGMarketingAgent" / "profiles"
    real = default_profiles_root()
    assert ROOT not in real.parents


def test_settings_profiles_dir_env_override(tmp_path, make_config):
    s = load_settings(make_config(), env_path=None, environ={"JG_PROFILES_DIR": str(tmp_path)})
    assert s.browser.profiles_root == tmp_path


def test_profile_in_use_reads_chrome_lockfile(tmp_path, monkeypatch):
    assert chrome.profile_in_use(tmp_path) is False  # 잠금 파일 없음
    (tmp_path / chrome.LOCK_FILE).write_bytes(b"")
    assert chrome.profile_in_use(tmp_path) is False  # 파일은 있지만 아무도 안 잡음
    if os.name == "nt":
        def locked(*_a, **_k):
            raise PermissionError(13, "in use")

        monkeypatch.setattr(chrome.os, "open", locked)
        assert chrome.profile_in_use(tmp_path) is True
        with pytest.raises(AppError) as exc:
            chrome.require_profile_free(tmp_path)
        assert str(exc.value.kind) == "profile_in_use"
        assert "그 프로필의 크롬 창을 닫아 주세요" in exc.value.action


def test_assist_args_open_url_only_without_automation(tmp_path):
    args = chrome.assist_args(
        Path("C:/Chrome/chrome.exe"), tmp_path / "profile-1",
        "https://www.youtube.com/watch?v=AAAAAAAAAA1", (60, -1060),
    )
    assert args[0].endswith("chrome.exe")
    assert f"--user-data-dir={tmp_path / 'profile-1'}" in args
    assert "--window-position=60,-1060" in args
    assert args[-1] == "https://www.youtube.com/watch?v=AAAAAAAAAA1"
    for word in ("remote-debugging", "enable-automation", "headless", "load-extension"):
        assert not any(word in a for a in args)


def test_popen_launcher_uses_argument_list_without_shell(monkeypatch):
    seen = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    chrome.popen_launcher(["chrome.exe", "--user-data-dir=x", "https://example.test/?a=1&b=2"])
    assert seen["args"] == ["chrome.exe", "--user-data-dir=x", "https://example.test/?a=1&b=2"]
    assert seen["kwargs"]["shell"] is False


def test_stop_process_ignores_finished_and_errors():
    class Done:
        def poll(self):
            return 0

        def terminate(self):
            raise AssertionError("끝난 프로세스는 건드리지 않는다")

    chrome.stop_process(Done())
    chrome.stop_process(None)


# ---------------------------------------------------------------- Playwright는 sandbox 주소만


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8765/sandbox/watch?v=AAAAAAAAAA1",
        "http://localhost:51234/sandbox/watch?v=AAAAAAAAAA1&profile=x",
    ],
)
def test_sandbox_urls_are_allowed(url):
    assert is_sandbox_url(url) and require_sandbox_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=AAAAAAAAAA1",
        "http://www.youtube.com/sandbox/watch?v=AAAAAAAAAA1",
        "https://youtu.be/AAAAAAAAAA1",
        "https://127.0.0.1:8765/sandbox/watch",
        "http://127.0.0.1:8765/watch?v=AAAAAAAAAA1",
        "http://127.0.0.1.example.com/sandbox/watch",
        "http://evil.test/sandbox/watch",
        "javascript:alert(1)",
    ],
)
def test_other_urls_are_refused(url):
    assert not is_sandbox_url(url)
    with pytest.raises(ValueError):
        require_sandbox_url(url)


def test_driver_refuses_youtube_before_starting_a_browser(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)  # 열려고 하면 ImportError
    driver = PlaywrightSandboxDriver(headless=True, window_position=(60, -1060))
    with pytest.raises(ValueError):
        driver.open(tmp_path, "https://www.youtube.com/watch?v=AAAAAAAAAA1")
    assert driver.visited == []


def test_page_may_only_load_local_addresses():
    assert is_local_url("http://127.0.0.1:8765/static/css/sandbox.css")
    assert is_local_url("about:blank")
    assert not is_local_url("https://www.youtube.com/")
    assert not is_local_url("https://fonts.googleapis.com/css")


def test_driver_launch_args_have_window_position():
    headed = PlaywrightSandboxDriver(headless=False, window_position=(-1860, 60))
    assert "--window-position=-1860,60" in headed.launch_args()
    assert "--window-size=1280,900" in headed.launch_args()
    headless = PlaywrightSandboxDriver(headless=True, window_position=(60, -1060))
    assert "--window-size=1280,900" not in headless.launch_args()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_only_the_sandbox_driver_uses_playwright():
    users = sorted(
        p.relative_to(APP).as_posix()
        for p in APP.rglob("*.py")
        if any(n.startswith("playwright") for n in _imports(p))
    )
    assert users == ["browser/sandbox_driver.py"]


def test_no_code_touches_real_youtube_pages():
    """실제 유튜브 화면을 찾거나 누르는 코드가 없다(DESIGN 6.1).

    Playwright를 쓰는 모듈에는 유튜브 주소가 없고,
    유튜브 주소를 쓰는 모듈은 Playwright를 쓰지 않는다.
    """
    driver_src = (APP / "browser" / "sandbox_driver.py").read_text(encoding="utf-8")
    code_lines = [
        line for line in driver_src.splitlines()
        if not line.strip().startswith(("#", "-", '"', "'")) and "youtube" in line.lower()
    ]
    assert code_lines == []
    for path in APP.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        if "youtube.com" in src:
            assert not any(n.startswith("playwright") for n in _imports(path)), path
    js = "\n".join(p.read_text(encoding="utf-8") for p in (APP / "static" / "js").glob("*.js"))
    for word in ("ytd-", "yt-formatted", "#contenteditable-root", "simplebox"):
        assert word not in js
