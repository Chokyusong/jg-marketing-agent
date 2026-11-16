"""scripts/check_secrets.py가 비밀값과 커밋 금지 파일을 잡는지 확인한다.

가짜 키는 실행할 때 조립한다. 이 파일에 키 모양 문자열을 그대로 두면 검사에 걸린다.
"""

import pytest

from scripts import check_secrets as cs

FAKE_GOOGLE_KEY = "AI" + "za" + "x" * 35
FAKE_GITHUB_TOKEN = "gh" + "p_" + "A" * 36
FAKE_PAT = "github" + "_pat_" + "B" * 30
FAKE_PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (f'key = "{FAKE_GOOGLE_KEY}"', "Google API 키"),
        (f"token={FAKE_GITHUB_TOKEN}", "GitHub 토큰"),
        (f"token={FAKE_PAT}", "GitHub 세분화 토큰"),
        (FAKE_PRIVATE_KEY, "개인키 블록"),
    ],
)
def test_detects_secret_content(text, kind):
    findings = cs.check_text("app/x.py", text)
    assert [f.kind for f in findings] == [kind]


def test_finding_does_not_print_full_secret():
    findings = cs.check_text("app/x.py", FAKE_GOOGLE_KEY)
    assert FAKE_GOOGLE_KEY not in str(findings[0])


def test_clean_text_passes():
    text = 'YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")\n# AIza 로 시작하는 키\n'
    assert cs.check_text("app/x.py", text) == []


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "sub/.env.local",
        "data/app.db",
        "data/app.sqlite3",
        "track-2-marketing-agent.pdf",
        "profiles/profile-1/Preferences",
    ],
)
def test_forbidden_paths(path):
    assert cs.check_path(path)


@pytest.mark.parametrize("path", [".env.example", "app/main.py", "docs/DESIGN.md"])
def test_allowed_paths(path):
    assert cs.check_path(path) == []


def test_env_example_with_filled_secret_fails():
    text = "YOUTUBE_API_KEY=abc123\nOLLAMA_MODEL=qwen2.5:7b\n"
    findings = cs.check_text(".env.example", text)
    assert len(findings) == 1
    assert "YOUTUBE_API_KEY" in findings[0].kind


def test_env_example_empty_secret_passes():
    text = "# 주석\nYOUTUBE_API_KEY=\nOLLAMA_BASE_URL=http://127.0.0.1:11434\n"
    assert cs.check_text(".env.example", text) == []


def test_binary_file_content_is_skipped():
    data = b"\x00\x01" + FAKE_GOOGLE_KEY.encode()
    assert cs.check_file("image.png", data) == []


def test_main_on_given_files(tmp_path, capsys):
    bad = tmp_path / "bad.py"
    bad.write_text(f"KEY = '{FAKE_GOOGLE_KEY}'\n", encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")
    assert cs.main([str(good)]) == 0
    assert cs.main([str(good), str(bad)]) == 1
    err = capsys.readouterr().err
    assert "Google API 키" in err
    assert FAKE_GOOGLE_KEY not in err


def test_repository_config_files_are_clean():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    files = cs.given_files([str(root / ".env.example"), str(root / "config.yaml")])
    assert cs.scan(files) == []
