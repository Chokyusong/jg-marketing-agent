"""R4 자막 자동 읽기(`app/transcript/auto.py`): 가짜 자막 목록으로만(실제 접속 없음).

- 언어 고르기: 한국어 올린 자막 > 한국어 자동 생성 > 다른 언어 올린 자막 > 다른 언어 자동 생성
- 줄마다 시간 표시, 짧은 조각 묶기, 20,000자 한도(앞 절반 + 뒤 절반, 줄 단위)
- 실패는 예외가 아니라 이유: 없음 · 꺼짐 · 막힘 · 시간 초과 · 영상 못 엶 · 라이브러리 오류
- 자막 글은 로그에 남지 않는다
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import pytest
import youtube_transcript_api as yta

from app.transcript import auto
from app.transcript.auto import (
    MIDDLE_CUT,
    AutoTranscriptProvider,
    choose_track,
    classify_failure,
    fit_lines,
    snippets_to_lines,
    source_label,
    stamp,
)
from app.transcript.manual import MAX_TRANSCRIPT_CHARS

VID = "BBBBBBBBBB2"


@dataclass
class Snip:
    text: str
    start: float
    duration: float = 2.0


@dataclass
class FakeTrack:
    language_code: str
    is_generated: bool
    snippets: list[Snip] = field(default_factory=list)
    error: BaseException | None = None
    language: str = ""

    def fetch(self):
        if self.error is not None:
            raise self.error
        return list(self.snippets)


def lister_of(*tracks: FakeTrack):
    calls: list[str] = []

    def lister(video_id: str):
        calls.append(video_id)
        return list(tracks)

    lister.calls = calls  # type: ignore[attr-defined]
    return lister


def raising(exc: BaseException):
    def lister(video_id: str):
        raise exc

    return lister


KO_SNIPS = [
    Snip("오늘은 연락 문제를", 1.0), Snip("얘기해 볼게요", 3.5),
    Snip("하루 한 번이면 될까요?", 83.4),
]


# ---------------------------------------------------------------- 고르기


def test_korean_uploaded_beats_korean_generated_and_others():
    tracks = [
        FakeTrack("en", False), FakeTrack("ko", True), FakeTrack("ko", False),
        FakeTrack("ja", True),
    ]
    chosen = choose_track(tracks)
    assert (chosen.language_code, chosen.is_generated) == ("ko", False)


def test_korean_generated_beats_other_language_uploaded():
    chosen = choose_track([FakeTrack("en", False), FakeTrack("ko", True)])
    assert (chosen.language_code, chosen.is_generated) == ("ko", True)


def test_other_language_uploaded_beats_other_generated():
    chosen = choose_track([FakeTrack("ja", True), FakeTrack("en", False)])
    assert (chosen.language_code, chosen.is_generated) == ("en", False)


def test_korean_region_code_counts_as_korean():
    chosen = choose_track([FakeTrack("en", False), FakeTrack("ko-KR", False)])
    assert chosen.language_code == "ko-KR"


def test_no_tracks_means_none():
    assert choose_track([]) is None


# ---------------------------------------------------------------- 글 만들기


@pytest.mark.parametrize(("sec", "text"), [(0, "0:00"), (83.4, "1:23"), (600, "10:00"),
                                           (3723, "1:02:03")])
def test_stamp(sec, text):
    assert stamp(sec) == text


def test_lines_keep_time_marks_and_group_short_pieces():
    lines = snippets_to_lines(KO_SNIPS)
    assert lines == ["0:01 오늘은 연락 문제를 얘기해 볼게요", "1:23 하루 한 번이면 될까요?"]


def test_lines_break_after_long_text():
    snips = [Snip("가" * 50, 0.0), Snip("나" * 50, 2.0)]
    assert snippets_to_lines(snips) == ["0:00 " + "가" * 50, "0:02 " + "나" * 50]


def test_lines_skip_empty_and_join_inner_newlines():
    snips = [Snip("  ", 0.0), Snip("첫 줄\n둘째 줄", 5.0)]
    assert snippets_to_lines(snips) == ["0:05 첫 줄 둘째 줄"]


def test_fit_lines_keeps_front_and_back_halves():
    lines = [f"{stamp(i * 10)} 줄 {i:05d} " + "가" * 40 for i in range(1000)]
    text = "\n".join(lines)
    assert len(text) > MAX_TRANSCRIPT_CHARS
    out, cut = fit_lines(text)
    assert cut and len(out) <= MAX_TRANSCRIPT_CHARS
    assert out.startswith(lines[0]) and out.endswith(lines[-1])
    assert MIDDLE_CUT in out
    head, tail = out.split(MIDDLE_CUT)
    assert abs(len(head) - len(tail)) < 200  # 거의 절반씩
    assert all(line in lines for line in out.split("\n") if line and line != MIDDLE_CUT)


def test_fit_lines_leaves_short_text():
    assert fit_lines("0:01 짧다") == ("0:01 짧다", False)


@pytest.mark.parametrize(("lang", "gen", "label"), [
    ("ko", True, "한국어, 자동 생성"), ("ko", False, "한국어, 올린 자막"),
    ("en", False, "영어, 올린 자막"),
    ("xx", True, "xx, 자동 생성"), ("ja", None, "일본어"),
])
def test_source_label(lang, gen, label):
    assert source_label(lang, gen) == label


# ---------------------------------------------------------------- 공급자: 성공


def test_korean_transcript_read():
    provider = AutoTranscriptProvider(lister_of(FakeTrack("ko", False, KO_SNIPS)))
    result = provider.read(VID)
    assert result.ok and result.reason == "" and result.note == ""
    t = result.transcript
    assert (t.source, t.language, t.generated) == ("auto", "ko", False)
    assert t.text == "0:01 오늘은 연락 문제를 얘기해 볼게요\n1:23 하루 한 번이면 될까요?"
    assert provider.fetch(VID) == t  # TranscriptProvider 규격


def test_only_generated_korean():
    result = AutoTranscriptProvider(lister_of(FakeTrack("ko", True, KO_SNIPS))).read(VID)
    assert (result.transcript.language, result.transcript.generated) == ("ko", True)


def test_only_other_language_keeps_language():
    snips = [Snip("Today we talk about texting", 2.0)]
    result = AutoTranscriptProvider(lister_of(FakeTrack("en", True, snips))).read(VID)
    assert (result.transcript.language, result.transcript.generated) == ("en", True)
    assert result.transcript.text == "0:02 Today we talk about texting"


def test_long_transcript_cut_with_note():
    snips = [Snip(f"조각 {i} " + "가" * 70, i * 20.0) for i in range(400)]
    result = AutoTranscriptProvider(lister_of(FakeTrack("ko", False, snips))).read(VID)
    assert result.ok and result.cut
    assert len(result.transcript.text) <= MAX_TRANSCRIPT_CHARS
    assert "앞부분과 뒷부분" in result.note


# ---------------------------------------------------------------- 공급자: 실패는 이유로


@pytest.mark.parametrize(("lister", "reason", "word"), [
    (lister_of(), "none", "자막이 없습니다"),
    (raising(yta.NoTranscriptFound(VID, ["ko"], None)), "none", "자막이 없습니다"),
    (raising(yta.TranscriptsDisabled(VID)), "disabled", "꺼 두었습니다"),
    (raising(yta.RequestBlocked(VID)), "blocked", "막았습니다"),
    (raising(yta.IpBlocked(VID)), "blocked", "막았습니다"),
    (raising(yta.PoTokenRequired(VID)), "blocked", "막았습니다"),
    (raising(yta.VideoUnavailable(VID)), "unavailable", "열 수 없어"),
    (raising(yta.AgeRestricted(VID)), "unavailable", "열 수 없어"),
    (raising(TimeoutError()), "timeout", "제한 시간"),
    (raising(ConnectionError("x")), "error", "문제가 생겼습니다"),
    (raising(RuntimeError("라이브러리 내부 오류")), "error", "문제가 생겼습니다"),
    (raising(ImportError("no module")), "missing", "설치되지 않았습니다"),
])
def test_failures_are_reasons_not_errors(lister, reason, word):
    result = AutoTranscriptProvider(lister).read(VID)
    assert not result.ok and result.transcript is None
    assert result.reason == reason
    assert word in result.note


def test_requests_timeout_and_connection_error():
    import requests

    assert classify_failure(requests.exceptions.ReadTimeout()) == "timeout"
    assert classify_failure(requests.exceptions.ConnectionError()) == "network"


def test_track_fetch_error_is_reason():
    track = FakeTrack("ko", False, error=yta.RequestBlocked(VID))
    assert AutoTranscriptProvider(lister_of(track)).read(VID).reason == "blocked"


def test_empty_snippets_mean_empty():
    track = FakeTrack("ko", False, [Snip("   ", 0.0)])
    assert AutoTranscriptProvider(lister_of(track)).read(VID).reason == "empty"


def test_slow_source_times_out_quickly():
    def slow(video_id):
        time.sleep(2)
        return [FakeTrack("ko", False, KO_SNIPS)]

    provider = AutoTranscriptProvider(slow, timeout_seconds=0.1, grace_seconds=0.0)
    started = time.monotonic()
    result = provider.read(VID)
    assert result.reason == "timeout"
    assert time.monotonic() - started < 1.5


def test_default_lister_is_replaced_in_tests():
    # tests/conftest.py가 실제 접속을 막는다: 가짜 공급처를 주지 않으면 「자막 없음」
    assert AutoTranscriptProvider().read(VID).reason == "none"


def test_library_lister_builds_session_with_timeout(monkeypatch):
    # 실제 접속 없이: 라이브러리에 넘기는 Session이 요청마다 제한 시간을 건다
    seen = {}

    class FakeApi:
        def __init__(self, http_client=None, proxy_config=None):
            seen["client"] = http_client

        def list(self, video_id):
            seen["video_id"] = video_id
            return [FakeTrack("ko", False, KO_SNIPS)]

    monkeypatch.setattr(yta, "YouTubeTranscriptApi", FakeApi)
    tracks = auto.library_lister(7.5)(VID)
    assert seen["video_id"] == VID and len(list(tracks)) == 1
    session = seen["client"]

    captured = {}

    def fake_request(self, method, url, **kwargs):
        captured.update(kwargs)
        return "ok"

    import requests

    monkeypatch.setattr(requests.Session, "request", fake_request)
    assert session.request("GET", "https://example.invalid/") == "ok"
    assert captured["timeout"] == 7.5


def test_transcript_text_never_logged(caplog):
    caplog.set_level(logging.DEBUG, logger="app.transcript.auto")
    AutoTranscriptProvider(lister_of(FakeTrack("ko", False, KO_SNIPS))).read(VID)
    AutoTranscriptProvider(raising(RuntimeError("비밀 같은 자막 글"))).read(VID)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "연락 문제" not in logged and "비밀 같은 자막 글" not in logged
    assert VID in logged
