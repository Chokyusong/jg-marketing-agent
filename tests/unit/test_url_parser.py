"""유튜브 링크 → 영상 ID (STAGES 2단계 완료 기준: 주소 형태와 잘못된 주소)."""

import pytest

from app.errors import AppError, ErrorKind
from app.youtube.url_parser import is_video_id, parse_video_id, watch_url

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "text",
    [
        # 영상 ID만
        VID,
        f"  {VID}  ",
        # watch?v=
        f"https://www.youtube.com/watch?v={VID}",
        f"http://youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}",
        f"www.youtube.com/watch?v={VID}",
        f"youtube.com/watch?v={VID}",
        f"HTTPS://WWW.YOUTUBE.COM/watch?v={VID}",
        # 시간·목록 꼬리표
        f"https://www.youtube.com/watch?v={VID}&t=42s",
        f"https://www.youtube.com/watch?v={VID}&list=PL0123456789abcdef&index=3",
        f"https://www.youtube.com/watch?feature=share&v={VID}",
        f"https://www.youtube.com/watch?v={VID}#t=1m10s",
        # youtu.be
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?t=90",
        f"https://youtu.be/{VID}?si=AbCdEfGh123&t=5",
        f"youtu.be/{VID}",
        # shorts / embed / live / v
        f"https://www.youtube.com/shorts/{VID}",
        f"https://youtube.com/shorts/{VID}?feature=share",
        f"https://www.youtube.com/embed/{VID}?start=10",
        f"https://www.youtube-nocookie.com/embed/{VID}",
        f"https://www.youtube.com/live/{VID}?si=xyz",
        f"https://www.youtube.com/v/{VID}",
        f"https://www.youtube.com/shorts/{VID}/",
    ],
)
def test_parses_supported_forms(text):
    assert parse_video_id(text) == VID


def test_keeps_dash_and_underscore_ids():
    assert parse_video_id("https://youtu.be/a-b_c-d_e-f") == "a-b_c-d_e-f"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "연애 고민",
        "dQw4w9WgXc",  # 10자
        "dQw4w9WgXcQQ",  # 12자
        "dQw4w9WgX!Q",  # 허용하지 않는 문자
        "https://www.youtube.com/",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/playlist?list=PL0123456789abcdef",
        "https://www.youtube.com/@somechannel",
        "https://www.youtube.com/channel/UC0123456789abcdefghij",
        "https://www.youtube.com/shorts/",
        "https://youtu.be/",
        "https://vimeo.com/123456789",
        f"https://example.com/watch?v={VID}",
        f"https://youtube.com.evil.test/watch?v={VID}",
        f"ftp://youtube.com/watch?v={VID}",
        f"javascript:alert('{VID}')",
    ],
)
def test_rejects_invalid(text):
    with pytest.raises(AppError) as info:
        parse_video_id(text)
    assert info.value.kind is ErrorKind.INVALID_URL
    assert info.value.http_status == 422


def test_helpers():
    assert is_video_id(VID)
    assert not is_video_id("x")
    assert watch_url(VID) == f"https://www.youtube.com/watch?v={VID}"
