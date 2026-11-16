"""오류 문구와 키 가리기."""

from app.errors import ERROR_TEXTS, AppError, ErrorKind, redact

FAKE_KEY = "AIza" + "x" * 35


def test_every_kind_has_korean_message_and_action():
    for kind in ErrorKind:
        text = ERROR_TEXTS[kind]
        assert text.message and text.action
        assert 400 <= text.http_status < 600


def test_youtube_six_kinds_exist():
    six = {
        "missing_key",
        "key_rejected",
        "quota_exceeded",
        "comments_disabled",
        "video_not_found",
        "network",
    }
    assert six <= {k.value for k in ErrorKind}


def test_app_error_dict():
    err = AppError(ErrorKind.QUOTA_EXCEEDED, detail="HTTP 403 quotaExceeded")
    data = err.to_dict()
    assert data["kind"] == "quota_exceeded"
    assert data["detail"] == "HTTP 403 quotaExceeded"
    assert "할당량" in data["message"]


def test_redact_key_param_and_secret_values():
    url = f"https://www.googleapis.com/youtube/v3/search?q=a&key={FAKE_KEY}&part=id"
    cleaned = redact(url)
    assert FAKE_KEY not in cleaned
    assert "key=***&part=id" in cleaned
    assert redact(f"oops {FAKE_KEY} oops", [FAKE_KEY]) == "oops *** oops"
    assert redact("KEY=abc def") == "KEY=*** def"
