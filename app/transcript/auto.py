"""자막 자동 읽기(R4): 영상을 고르면 그 영상의 자막을 가져온다.

과제: "AI가 자막(없으면 제목·설명)과 인기 댓글을 읽고".

가져오는 방법은 구현 전에 문서로 확인했다(2026-11-17).

- 라이브러리: `youtube-transcript-api` 1.2.5 (2026-11-05 공개, MIT 라이선스,
  `requires_python >=3.8,<3.16`, 분류에 Python 3.12 있음, 의존 `requests`·`defusedxml`).
  출처: https://pypi.org/project/youtube-transcript-api/ (PyPI JSON
  https://pypi.org/pypi/youtube-transcript-api/json), https://github.com/jdepoix/youtube-transcript-api
- 문서대로 쓰는 법
  - `YouTubeTranscriptApi(proxy_config=None, http_client=None)` — 인스턴스를 만들어 쓴다.
    `http_client`에 `requests.Session`을 넘길 수 있다(여기서는 요청마다 제한 시간을 거는 Session).
    스레드 하나에 인스턴스 하나(문서: thread-safe 아님) — 그래서 부를 때마다 새로 만든다.
  - `.list(video_id)` → `TranscriptList`(반복하면 사람이 올린 자막 다음 자동 생성 자막).
    `Transcript`의 `language`·`language_code`·`is_generated`, `.fetch()` → `FetchedTranscript`
    (조각마다 `text`·`start`(초)·`duration`).
  - 영상 ID를 넘긴다(주소가 아니라). 예외: `TranscriptsDisabled`, `NoTranscriptFound`,
    `VideoUnavailable`, `VideoUnplayable`, `AgeRestricted`, `InvalidVideoId`, `RequestBlocked`,
    `IpBlocked`(RequestBlocked의 하위), `PoTokenRequired`, `YouTubeRequestFailed`,
    `CouldNotRetrieveTranscript`(위 모두의 상위). 설치한 패키지의 `__all__`로 이름을 확인했다.
  - 주의(문서): 유튜브 웹 화면이 쓰는 **공개되지 않은 경로**를 쓴다. 언제든 멈출 수 있고,
    클라우드 서버 IP는 대개 막힌다(`RequestBlocked`·`IpBlocked`). 라이브러리에 제한 시간 설정이 없어
    Session에 시간을 걸고, 전체도 따로 기다리는 시간을 둔다.

규칙
- 언어: 한국어 사람이 올린 자막 → 한국어 자동 생성 → 다른 언어 사람이 올린 자막 →
  다른 언어 자동 생성. 다른 언어를 쓰면 출처에 언어를 적는다.
- 줄마다 시간 표시(`1:23 …`)를 붙인다(근거 문장에서 장면을 짚게). 짧은 조각은 한 줄로 묶는다.
- 정리는 붙여 넣은 자막과 같은 `clean_transcript`, 20,000자를 넘으면 앞 절반 + 뒤 절반(줄 단위).
- 실패는 오류가 아니다. 자막 없음·꺼짐·막힘·시간 초과·라이브러리 오류 모두 `AutoResult.reason`과
  한국어 `note`로 돌려준다(로그에는 이유만 남기고 자막 글은 남기지 않는다).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from app.transcript.base import Transcript
from app.transcript.manual import MAX_TRANSCRIPT_CHARS, clean_transcript

log = logging.getLogger("app.transcript.auto")

DEFAULT_TIMEOUT_SECONDS = 10.0
PREFERRED_LANGUAGE = "ko"
MIDDLE_CUT = "…(중략)…"
LINE_MAX_CHARS = 80  # 시간 표시 한 줄에 묶는 글자 수(넘으면 다음 줄)
LINE_MAX_SECONDS = 15.0  # 한 줄이 덮는 시간(넘으면 다음 줄)

LANGUAGE_NAMES = {
    "ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어", "es": "스페인어",
    "fr": "프랑스어", "de": "독일어", "vi": "베트남어", "th": "태국어", "id": "인도네시아어",
    "pt": "포르투갈어",
    "ru": "러시아어", "it": "이탈리아어", "hi": "힌디어", "ar": "아랍어", "tr": "튀르키예어",
}

# 이유 코드 → 화면·기록에 남길 말. 실패해도 제목·설명으로 대신한다
REASON_NOTES = {
    "none": "이 영상에는 자막이 없습니다",
    "disabled": "영상 주인이 자막을 꺼 두었습니다",
    "unavailable": "영상을 열 수 없어 자막을 읽지 못했습니다(연령 제한·비공개 등)",
    "blocked": "유튜브가 자막 요청을 잠시 막았습니다",
    "timeout": "자막 응답이 제한 시간 안에 오지 않았습니다",
    "network": "인터넷 연결 문제로 자막을 읽지 못했습니다",
    "empty": "자막이 비어 있습니다",
    "error": "자막을 읽는 중 문제가 생겼습니다",
    "missing": "자막 읽기 도구가 설치되지 않았습니다",
    "off": "자막 자동 읽기가 꺼져 있습니다",
}
# 잠깐의 문제(시간이 지나면 될 수 있다). 이런 이유는 저장해 두되 얼마 뒤 다시 읽어 본다
TRANSIENT_REASONS = frozenset({"blocked", "timeout", "network", "error", "missing"})


def language_name(code: str) -> str:
    base = (code or "").split("-", 1)[0].lower()
    return LANGUAGE_NAMES.get(base, code or "언어 모름")


def source_label(language: str | None, generated: bool | None) -> str:
    """「한국어, 자동 생성」 / 「영어, 올린 자막」."""
    kind = "자동 생성" if generated else "올린 자막" if generated is False else ""
    name = language_name(language or "")
    return f"{name}, {kind}" if kind else name


# ---------------------------------------------------------------- 공급처 규격(가짜로 바꿀 수 있게)


class Snippet(Protocol):
    text: str
    start: float


class Track(Protocol):
    language_code: str
    is_generated: bool

    def fetch(self) -> Iterable[Snippet]: ...


Lister = Callable[[str], Iterable[Track]]


def _timeout_session(timeout: float) -> Any:
    import requests

    class TimeoutSession(requests.Session):
        """라이브러리가 부르는 요청마다 제한 시간을 건다(라이브러리에 시간 설정이 없다)."""

        def request(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
            kwargs.setdefault("timeout", timeout)
            return super().request(*args, **kwargs)

    return TimeoutSession()


def library_lister(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Lister:
    """`youtube-transcript-api`로 자막 목록을 읽는 함수. 부를 때마다 인스턴스를 새로 만든다."""

    def list_tracks(video_id: str) -> Iterable[Track]:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi(http_client=_timeout_session(timeout))
        return list(api.list(video_id))

    return list_tracks


def default_lister(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Lister:
    """실제 프로그램이 쓰는 공급처.

    테스트는 이 함수를 바꿔 실제 접속을 막는다(tests/conftest.py).
    """
    return library_lister(timeout)


# ---------------------------------------------------------------- 실패 분류


def classify_failure(exc: BaseException) -> str:
    """예외 → 이유 코드(`REASON_NOTES`의 키)."""
    if isinstance(exc, TimeoutError):
        return "timeout"
    try:
        import requests

        if isinstance(exc, requests.exceptions.Timeout):
            return "timeout"
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "network"
    except ImportError:  # pragma: no cover - requests는 라이브러리 의존이라 늘 있다
        pass
    try:
        import youtube_transcript_api as yta
    except ImportError:
        return "missing" if isinstance(exc, ImportError) else "error"
    if isinstance(exc, yta.TranscriptsDisabled):
        return "disabled"
    if isinstance(exc, yta.NoTranscriptFound):
        return "none"
    # IpBlocked는 RequestBlocked의 하위
    if isinstance(exc, (yta.RequestBlocked, yta.PoTokenRequired)):
        return "blocked"
    if isinstance(exc, (yta.VideoUnavailable, yta.VideoUnplayable, yta.AgeRestricted,
                        yta.InvalidVideoId)):
        return "unavailable"
    if isinstance(exc, yta.YouTubeRequestFailed):
        return "blocked" if "429" in str(exc) else "network"
    if isinstance(exc, ImportError):
        return "missing"
    return "error"


# ---------------------------------------------------------------- 고르기와 글 만들기


def _is_korean(track: Track) -> bool:
    return (track.language_code or "").split("-", 1)[0].lower() == PREFERRED_LANGUAGE


def choose_track(tracks: Iterable[Track]) -> Track | None:
    """한국어 올린 자막 → 한국어 자동 생성 → 다른 언어 올린 자막 → 다른 언어 자동 생성."""
    items = list(tracks)

    def rank(t: Track) -> int:
        return (0 if _is_korean(t) else 2) + (1 if t.is_generated else 0)

    return min(items, key=rank) if items else None  # min은 같은 순위면 앞의 것(목록 순서)


def stamp(seconds: float) -> str:
    """83.4 → `1:23`, 3723 → `1:02:03`."""
    total = max(0, int(seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def snippets_to_lines(snippets: Iterable[Snippet]) -> list[str]:
    """조각들을 `시간 글` 줄로. 짧은 조각은 80자·15초까지 한 줄로 묶는다."""
    lines: list[str] = []
    start: float | None = None
    parts: list[str] = []
    for snip in snippets:
        text = " ".join(str(getattr(snip, "text", "") or "").split())
        if not text:
            continue
        at = float(getattr(snip, "start", 0.0) or 0.0)
        if start is not None and (
            len(" ".join(parts)) + len(text) > LINE_MAX_CHARS or at - start > LINE_MAX_SECONDS
        ):
            lines.append(f"{stamp(start)} {' '.join(parts)}")
            start, parts = None, []
        if start is None:
            start = at
        parts.append(text)
    if start is not None and parts:
        lines.append(f"{stamp(start)} {' '.join(parts)}")
    return lines


def fit_lines(text: str, limit: int = MAX_TRANSCRIPT_CHARS) -> tuple[str, bool]:
    """한도를 넘으면 앞 절반 + 뒤 절반 줄을 남기고 가운데를 `…(중략)…` 한 줄로(3단계 규칙)."""
    if len(text) <= limit:
        return text, False
    lines = text.split("\n")
    budget = limit - len(MIDDLE_CUT) - 2
    half = budget // 2
    head: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > half:
            break
        head.append(line)
        used += len(line) + 1
    tail: list[str] = []
    used = 0
    for line in reversed(lines[len(head):]):
        if used + len(line) + 1 > budget - half:
            break
        tail.insert(0, line)
        used += len(line) + 1
    out = "\n".join([*head, MIDDLE_CUT, *tail])
    if len(out) > limit:  # 줄 하나가 아주 긴 극단적인 경우
        out = out[: limit - 1] + "…"
    return out, True


@dataclass(frozen=True)
class AutoResult:
    transcript: Transcript | None
    reason: str = ""  # 실패했을 때 이유 코드(REASON_NOTES)
    note: str = ""  # 화면·기록용 한 줄(성공이면 비어 있거나 「길어서 앞뒤만」)
    cut: bool = False

    @property
    def ok(self) -> bool:
        return self.transcript is not None


def failure(reason: str) -> AutoResult:
    return AutoResult(None, reason=reason, note=REASON_NOTES.get(reason, REASON_NOTES["error"]))


# ---------------------------------------------------------------- 공급자


class AutoTranscriptProvider:
    """`TranscriptProvider` 규격(`fetch`)을 따르는 자동 공급자. `read`가 이유까지 돌려준다."""

    name = "auto"

    def __init__(
        self,
        lister: Lister | None = None,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        grace_seconds: float = 2.0,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self.grace_seconds = float(grace_seconds)  # 요청마다 거는 시간 위에 전체로 더 기다리는 시간
        self._lister = lister  # None이면 읽을 때마다 default_lister(테스트가 바꿔 끼운다)

    def fetch(self, video_id: str) -> Transcript | None:
        return self.read(video_id).transcript

    def read(self, video_id: str) -> AutoResult:
        """자막을 읽는다. 무슨 일이 있어도 예외를 던지지 않고 `AutoResult`를 돌려준다."""
        box: dict[str, Any] = {}

        def work() -> None:
            try:
                box["result"] = self._read(video_id)
            except BaseException as exc:  # noqa: BLE001 - 어떤 실패든 「자막 없음」으로 넘긴다
                box["error"] = exc

        # 라이브러리 안에서 요청이 여러 번 이어질 수 있어 전체 시간도 따로 잰다
        # (데몬 스레드: 늦은 응답은 버리고, 프로그램을 닫을 때 기다리지 않는다)
        worker = threading.Thread(target=work, name="jg-transcript", daemon=True)
        worker.start()
        worker.join(self.timeout_seconds + self.grace_seconds)
        if worker.is_alive():
            result = failure("timeout")
        elif "error" in box:
            result = failure(classify_failure(box["error"]))
            if result.reason == "error":
                log.warning("자막 자동 읽기 실패 %s: %s", video_id, type(box["error"]).__name__)
        else:
            result = box.get("result") or failure("error")
        if result.ok:
            t = result.transcript
            assert t is not None
            log.info("자막 자동 읽기 %s: %d자 (%s)", video_id, len(t.text),
                     source_label(t.language, t.generated))
        else:
            log.info("자막 자동 읽기 %s: 못 읽음(%s)", video_id, result.reason)
        return result

    def _read(self, video_id: str) -> AutoResult:
        lister = self._lister or default_lister(self.timeout_seconds)
        track = choose_track(lister(video_id))
        if track is None:
            return failure("none")
        lines = snippets_to_lines(track.fetch())
        text = clean_transcript("\n".join(lines))
        if not text:
            return failure("empty")
        text, cut = fit_lines(text)
        transcript = Transcript(
            text=text,
            source="auto",
            language=track.language_code or None,
            generated=bool(track.is_generated),
        )
        note = "길어서 앞부분과 뒷부분만 저장했습니다" if cut else ""
        return AutoResult(transcript, note=note, cut=cut)
