"""R4 자막 자동 읽기가 맥락에 붙는 모습: 가짜 공급처로만(실제 접속 없음).

- 영상을 고르면(맥락을 만들면) 자막을 자동으로 읽는다. 응답에 글자 수·언어·자동 생성 여부
- 우선순위: 사람이 붙여 넣은 자막 > 자동으로 읽은 자막 > 없음(제목·설명)
- 붙여 넣은 것이 있으면 자동을 부르지 않는다. 저장된 것은 다시 부르지 않는다
- 못 읽으면 오류가 아니라 이유(transcript_note)와 함께 제목·설명으로. 잠깐의 문제만 30분 뒤 다시
- 「자막 자동으로 읽기」 끔(transcript.auto=false)이면 부르지 않는다
- 규칙 검사(current)는 바깥에 접속하지 않는다. 자동 생성 자막은 AI 입력 머리에 알려 둔다
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import youtube_transcript_api as yta
from test_context_api import VID, add_video_and_comments, services_of

from app.analysis.context import fit_prompt
from app.transcript import auto

SNIPS = [
    {"text": "오늘은 연락 문제를", "start": 1.0},
    {"text": "얘기해 볼게요", "start": 3.0},
    {"text": "하루 한 번이면 될까요?", "start": 83.0},
]


class Snip:
    def __init__(self, text, start):
        self.text, self.start, self.duration = text, start, 2.0


class Track:
    def __init__(self, code, generated, snips=SNIPS):
        self.language_code, self.is_generated, self.language = code, generated, code
        self._snips = snips

    def fetch(self):
        return [Snip(**s) for s in self._snips]


class FakeSource:
    """가짜 공급처. `tracks` 또는 `error`를 돌려주고 부른 횟수를 센다."""

    def __init__(self, tracks=(), error=None):
        self.tracks, self.error, self.calls = list(tracks), error, []

    def __call__(self, video_id):
        self.calls.append(video_id)
        if self.error is not None:
            raise self.error
        return self.tracks


@pytest.fixture
def source(monkeypatch):
    holder = {"src": FakeSource([Track("ko", True)])}

    def factory(timeout=10.0):
        return lambda video_id: holder["src"](video_id)

    monkeypatch.setattr(auto, "default_lister", factory)
    return holder


@pytest.fixture
def client(mock_http, fixture_json, fake_key, make_client):
    return make_client(add_video_and_comments(mock_http(), fixture_json), key=fake_key)


def test_selecting_video_reads_transcript_automatically(client, source):
    data = client.post(f"/api/videos/{VID}/context").json()
    assert data["transcript_source"] == "auto"
    assert data["body_source"] == "transcript"
    text = "0:01 오늘은 연락 문제를 얘기해 볼게요\n1:23 하루 한 번이면 될까요?"
    assert data["transcript_chars"] == len(text)
    assert (data["transcript_language"], data["transcript_generated"]) == ("ko", True)
    assert data["transcript_label"] == "한국어, 자동 생성"
    assert data["transcript_text"] == ""  # 자동으로 읽은 자막은 글 상자에 넣지 않는다
    assert data["transcript_reason"] == "" and data["auto_transcript"] is True
    ctx = services_of(client).context.current(VID)
    assert ctx.transcript_text == text
    # AI 입력: 출처와 「자동 생성이라 받아쓰기 틀림」 안내, 시간 표시가 그대로
    prompt = fit_prompt(ctx, 6000).text
    assert "[자막 · 자동으로 읽은 자막(한국어, 자동 생성) · 유튜브 자동 생성 자막" in prompt
    assert "1:23 하루 한 번이면 될까요?" in prompt
    assert "[안내] 자막이 없어" not in prompt


def test_other_language_shows_language(client, source):
    source["src"] = FakeSource([Track("en", False, [{"text": "Hello love", "start": 5.0}])])
    data = client.post(f"/api/videos/{VID}/context").json()
    assert data["transcript_source"] == "auto"
    assert data["transcript_label"] == "영어, 올린 자막"


def test_stored_auto_transcript_is_not_fetched_again(client, source):
    client.post(f"/api/videos/{VID}/context")
    client.post(f"/api/videos/{VID}/context")
    client.post(f"/api/videos/{VID}/context?refresh=true")  # 댓글을 새로 불러도 자막은 그대로
    services_of(client).context.current(VID)
    assert source["src"].calls == [VID]


def test_manual_transcript_wins_and_auto_is_not_called(client, source):
    res = client.put(f"/api/videos/{VID}/transcript", json={"text": "0:05 직접 넣은 자막"})
    data = res.json()
    assert data["transcript_source"] == "manual"
    assert data["transcript_text"] == "0:05 직접 넣은 자막"
    client.post(f"/api/videos/{VID}/context")
    assert source["src"].calls == []


def test_manual_over_stored_auto_then_clear_reads_again(client, source):
    assert client.post(f"/api/videos/{VID}/context").json()["transcript_source"] == "auto"
    data = client.put(f"/api/videos/{VID}/transcript", json={"text": "0:05 직접 넣은 자막"}).json()
    assert data["transcript_source"] == "manual"
    assert len(source["src"].calls) == 1
    data = client.delete(f"/api/videos/{VID}/transcript").json()
    assert data["transcript_source"] == "auto"  # 지우면 자동으로 다시 읽는다
    assert len(source["src"].calls) == 2


@pytest.mark.parametrize(("error", "tracks", "reason", "word"), [
    (None, [], "none", "자막이 없습니다"),
    (yta.TranscriptsDisabled(VID), (), "disabled", "꺼 두었습니다"),
    (yta.RequestBlocked(VID), (), "blocked", "막았습니다"),
    (TimeoutError(), (), "timeout", "제한 시간"),
])
def test_failure_falls_back_to_title_and_description(client, source, error, tracks, reason, word):
    source["src"] = FakeSource(tracks, error)
    res = client.post(f"/api/videos/{VID}/context")
    assert res.status_code == 200
    data = res.json()
    assert data["transcript_source"] == "none"
    assert data["body_source"] == "title_description"
    assert data["transcript_reason"] == reason
    assert word in data["transcript_note"]
    prompt = fit_prompt(services_of(client).context.current(VID), 6000).text
    assert "[안내] 자막이 없어" in prompt


def test_permanent_failure_is_not_retried(client, source):
    source["src"] = FakeSource([], None)
    for _ in range(3):
        client.post(f"/api/videos/{VID}/context")
    client.post(f"/api/videos/{VID}/context?refresh=true")
    assert len(source["src"].calls) == 1


def test_transient_failure_retried_after_30_minutes_or_refresh(client, source, clock):
    source["src"] = FakeSource((), yta.RequestBlocked(VID))
    client.post(f"/api/videos/{VID}/context")
    client.post(f"/api/videos/{VID}/context")
    assert len(source["src"].calls) == 1  # 막힌 직후에는 다시 부르지 않는다
    client.post(f"/api/videos/{VID}/context?refresh=true")
    assert len(source["src"].calls) == 2  # 다시 만들면 한 번 더
    services = services_of(client)
    later = services.context.clock() + timedelta(minutes=31)
    services.context.clock = lambda: later
    source["src"] = FakeSource([Track("ko", False)])
    data = client.post(f"/api/videos/{VID}/context").json()
    assert data["transcript_source"] == "auto" and data["transcript_label"] == "한국어, 올린 자막"


def test_current_never_fetches(client, source):
    services = services_of(client)
    services.videos.get(VID)
    # 아직 맥락을 만들지 않았으면 current가 build로 만든다(그때 한 번 읽는다)
    services.context.current(VID)
    assert len(source["src"].calls) == 1
    for _ in range(5):
        services.context.current(VID)
    assert len(source["src"].calls) == 1


def test_auto_off_setting_does_not_call(mock_http, fixture_json, fake_key, make_client, source):
    client = make_client(
        add_video_and_comments(mock_http(), fixture_json), key=fake_key,
        overrides={"transcript": {"provider": "auto", "auto": False}},
    )
    data = client.post(f"/api/videos/{VID}/context").json()
    assert data["transcript_source"] == "none"
    assert data["transcript_reason"] == "off" and data["auto_transcript"] is False
    assert source["src"].calls == []


def test_manual_provider_setting_means_auto_off(mock_http, fixture_json, fake_key, make_client,
                                                source):
    client = make_client(
        add_video_and_comments(mock_http(), fixture_json), key=fake_key,
        overrides={"transcript": {"provider": "manual"}},
    )
    assert client.post(f"/api/videos/{VID}/context").json()["transcript_reason"] == "off"
    assert source["src"].calls == []


def test_auto_transcript_not_in_any_log(client, source, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    client.post(f"/api/videos/{VID}/context")
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "연락 문제" not in logged
