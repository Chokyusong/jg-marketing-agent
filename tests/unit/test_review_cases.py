"""맥락 검수 회귀 사례(2026-11-18 대표, `tests/fixtures/story_review_cases.json`)와 그것을 진짜 검수
AI에 돌리는 `scripts/review_cases.py`를 **가짜**로만 시험한다(인터넷·AI 없음).

진짜 검수 AI로 돌리는 것은 사람이 스크립트로 한다(--db 앱 DB 사본). 기대: 테라 7·9·10·15·17은
통과, 8·21·22는 걸림(사주를 꺼내려고 지어낸 궁금증 — 용기 낼 때 · 표현 방식). 대표 기준
예시(2026-11-18)도 통과.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import review_cases as RC  # noqa: E402

from app.analysis import review as rv  # noqa: E402


def test_fixture_holds_the_eight_cases_the_boss_picked():
    data = RC.load_cases()
    assert data["brand"] == "운명원"
    cases = {c["case"]: c for c in data["cases"]}
    assert sorted(n for n, c in cases.items() if c["expect"] == "pass") == sorted(
        ["boss-example", "terra-7", "terra-9", "terra-10", "terra-15", "terra-17"])
    # 대표 기준 예시(2026-11-18)는 terra-7·8과 같은 영상, 대표가 쓴 그대로
    assert cases["boss-example"]["video_id"] == cases["terra-7"]["video_id"]
    assert "저도 비슷한상황이라" in cases["boss-example"]["body"]
    assert sorted(n for n, c in cases.items() if c["expect"] == "flag") == sorted(
        ["terra-8", "terra-21", "terra-22"])
    for c in cases.values():
        assert c["video_id"] and c["body"] and c["why"]
        assert not c["body"].startswith("[광고]")  # 검수는 표기를 뺀 본문을 본다
        assert "운명원" in c["body"]
    # 영상 자료(자막·설명·인기 댓글)는 저장소에 넣지 않는다 — DB 사본에서 읽는다
    for c in cases.values():
        assert not {"transcript", "description", "comments", "material"} & set(c)


def test_bad_expect_is_refused(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text('{"brand": "운명원", "cases": [{"case": "x", "expect": "maybe"}]}',
                    encoding="utf-8")
    try:
        RC.load_cases(path)
    except ValueError as exc:
        assert "x" in str(exc)
    else:
        raise AssertionError("pass/flag 말고는 받지 않는다")


class FakeContext:
    def current(self, vid):
        video = SimpleNamespace(title=f"제목 {vid}", description="설명")
        return SimpleNamespace(video=SimpleNamespace(video=video), transcript_text="자막",
                               comments=[SimpleNamespace(text="인기 댓글")])


def fake_services():
    return SimpleNamespace(context=FakeContext(), require_llm=lambda: "llm")


def test_review_one_asks_with_the_app_prompts_and_compares():
    seen: dict = {}

    def ask(llm, *, system, user, story):
        seen.update(llm=llm, system=system, user=user, story=story)
        return rv.Verdict(False, ["끊긴 곳: 사진 → 표현 방식: 지어낸 궁금증"],
                          {"same_topic": True, "flow": False, "natural_ad": False,
                           "link_reason": "", "break_at": "사진 → 표현 방식: 지어낸 궁금증"})

    case = {"case": "terra-21", "expect": "flag", "video_id": "VID", "concern": "고민",
            "key_phrases": ["말"], "evidence": "근거", "body": "본문 운명원"}
    row = RC.review_one(fake_services(), case, brand="운명원", ask=ask)
    assert seen["story"] is True and seen["llm"] == "llm"
    assert seen["system"] == rv.review_system(brand="운명원", story=True)
    assert "본문 운명원" in seen["user"] and "제목 VID" in seen["user"]
    assert "자막" in seen["user"] and "인기 댓글" in seen["user"]  # 앱과 같은 영상 자료
    assert row["got"] == "flag" and row["match"] is True
    assert row["break_at"].startswith("사진 → 표현 방식")
    md = RC.table([row, {**row, "case": "terra-7", "expect": "pass", "match": False}],
                  label="고친 검수기")
    assert md.startswith("### 고친 검수기")
    assert "| terra-21 | flag | flag | ○ |" in md and "| terra-7 | pass | flag | ✗ |" in md
    assert md.endswith("기대대로 1/2")


def test_review_one_reports_an_ai_error_as_a_row():
    def ask(*_, **__):
        raise ValueError("JSON이 아님")

    case = {"case": "terra-7", "expect": "pass", "video_id": "VID", "body": "본문 운명원"}
    row = RC.review_one(fake_services(), case, brand="운명원", ask=ask)
    assert row["got"] == "error" and row["match"] is False and "JSON" in row["error"]
