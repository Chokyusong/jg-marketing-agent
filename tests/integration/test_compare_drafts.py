"""초안 전후 비교 스크립트(scripts/compare_drafts.py)를 가짜 LLM으로 돌린다(AI·인터넷 없이).

- 글 쓰는 AI는 앱과 같은 `build_llm(settings)`로 고른다(`llm.active`·모델만 바꾼다).
- 영상마다 초안 N개, 처음 통과한 초안 승인, 시도별 글·다시 쓰기 까닭을 남긴다.
- 표(2026-11-18 지시서 7절): 초안마다 말 높임·들은 경로·기분·알고 싶은 것과 갈래·고민·댓글·검수·
  다시 쓴 횟수와 까닭·최종 실패, 지표(첫 시도 통과·첫 검수 통과·갈래·끝말 같은 것 등).
"""

import json
import tempfile
from pathlib import Path

import httpx
import pytest

from app import db
from app.api.deps import build_services
from app.errors import AppError, ErrorKind
from app.llm.registry import build_llm
from scripts import compare_drafts as C
from scripts import eval_drafts as E

CONTEXTS = Path(__file__).resolve().parent.parent / "fixtures" / "contexts"


def _llm_off(request):
    raise httpx.ConnectError("AI 꺼짐(테스트)", request=request)


def test_settings_switch_only_the_writing_ai_and_its_model(tmp_db_path):
    s = C.make_settings("ollama", tmp_db_path, model="small:1b", environ={})
    assert s.llm.active == "ollama" and s.llm.ollama_model == "small:1b"
    assert s.youtube_api_key and s.youtube_api_key.startswith("AIza")  # 가짜 키(실행할 때 조립)
    other = C.make_settings("claude", tmp_db_path, model="some-model", environ={})
    assert other.llm.active == "claude" and other.llm.model_for("claude") == "some-model"
    # 앱과 같은 등록부로 만든다: 없는 이름이면 앱과 같은 오류
    with pytest.raises(AppError) as err:
        build_llm(C.make_settings("no-such-ai", tmp_db_path, environ={}))
    assert err.value.kind == ErrorKind.LLM_PROVIDER_UNKNOWN


def test_args_need_contexts_and_a_db_for_real_videos():
    with pytest.raises(SystemExit):
        C.parse_args(["--ai", "ollama"])
    with pytest.raises(SystemExit):
        C.parse_args(["--ai", "ollama", "--videos", "abc"])
    args = C.parse_args(["--ai", "ollama", "--fixtures", "EvalCtx0001", "--labels", "7회차,8회차"])
    assert args.drafts == 2 and args.db is None and args.labels == "7회차,8회차"


def test_run_and_table_with_fake_llm(tmp_db_path, fake_llm):
    contexts = E.load_contexts(CONTEXTS, limit=1)
    vid = contexts[0]["video_id"]
    quote_a = "만나도 각자 휴대폰만 봐요"
    quote_b = "같은 식당, 같은 카페에서 끝나요"
    analysis = {"topic": "권태기", "concern": "설렘이 사라진 3년 연애", "tone": "차분",
                "viewer_needs": "권태기를 넘기는 법",
                "evidence": [{"quote": quote_a, "source": "transcript"},
                             {"quote": quote_b, "source": "transcript"}]}
    good_a = (f"'{quote_a}'라는 말이 오래 남네요. 요즘 운명원 연애 사주 잘 본다던데 "
              "저도 이 사람이랑 끝까지 갈지 보러 가 보려고요.")
    good_b = ("같은 식당, 같은 카페에서 데이트가 끝난다는 말에 공감했어요. "
              "운명원이 연애 사주 잘 본다길래 우리 궁합 어떤지 보러 가려고요.")
    llm = fake_llm([analysis,
                    {"mood": "답답", "body": "연애 사주 상담을 받아 보세요.", "wish": "",
                     "used_quote": ""},
                    {"mood": "씁쓸", "body": good_a, "wish": "끝까지 갈지",
                     "used_quote": quote_a},
                    {"ok": True, "problems": [], "wish_kind": "궁합"},
                    {"mood": "공감", "body": good_b, "wish": "우리 궁합",
                     "used_quote": quote_b},
                    {"ok": False, "problems": ["알고 싶은 것이 고민과 다름"],
                     "wish_kind": "궁합"},
                    {"mood": "공감", "body": good_b.replace("우리 궁합", "우리 둘 궁합"),
                     "wish": "우리 둘 궁합", "used_quote": quote_b},
                    {"ok": True, "problems": [], "wish_kind": "궁합"}])
    llm.model = "fake"
    settings = C.make_settings("ollama", tmp_db_path, model="fake", environ={})
    services = build_services(settings, transport=E.youtube_transport(contexts),
                              llm_transport=httpx.MockTransport(_llm_off))
    services.llm = llm
    try:
        E.prepare(services, contexts)
        videos = C.run(services, [vid], drafts_per_video=2,
                       titles={vid: contexts[0]["title"]}, log=lambda s: None)
        rules = services.drafts.rules
        facts = services.drafts.brand_facts
    finally:
        services.llm = None
        services.close()

    (row,) = videos
    first, second = row["drafts"]
    assert (first["attempts"], first["passed"], first["first_passed"]) == (2, True, False)
    assert first["retry_reasons"] and first["retry_reasons"][0]  # 다시 쓰게 한 까닭이 남는다
    assert [a["body"] for a in first["run"]["attempts"]][-1] == first["body"]
    assert first["voice"] and first["heard"] and first["mood"] == "씁쓸"
    # 글자 수는 V1처럼 광고 표기를 뺀 본문
    assert first["body"].startswith("[광고] ")
    assert first["chars"] == len(first["body"]) - len("[광고] ")
    assert first["wish"] == "끝까지 갈지" and first["wish_kind"] == "궁합"
    assert second["quote"] == quote_b and second["review"] == "rewritten"
    assert second["review_first"] == ["알고 싶은 것이 고민과 다름"]

    table = C.markdown_table(videos, brand=rules.brand, disclosure=rules.disclosure, facts=facts)
    assert "| 영상 | # | 말 높임 · 들은 경로 · 기분 |" in table
    assert "끝까지 갈지 (궁합)" in table
    assert "| 첫 시도 규칙 검사 통과 | 1/2 |" in table
    assert "| 첫 검수 통과 | 1/2 |" in table
    assert "| 알고 싶은 것 갈래 | 궁합 2 |" in table
    assert "AI 검수 1" in table and "V1 1" in table
    # 전·후 나란히: 예전 결과의 같은 영상 초안 옆에 놓는다
    before = [{"video_id": vid, "drafts": [{"n": 1, "body": "[광고] 예전 글", "chars": 9,
                                            "passed": True, "first_passed": True,
                                            "attempts": 1, "seconds": 1.0}]}]
    both = C.markdown_table(videos, before=before, labels=("7회차", "8회차"), facts=facts)
    assert "| 영상 | # | 7회차 | 8회차 |" in both
    assert "[광고] 예전 글 (9자 · 통과 · 1번째)" in both


# ------------------------------------------------ 2026-11-17 --db 경로(Windows WinError 32)

ANALYSIS = {"topic": "권태기", "concern": "설렘이 사라진 3년 연애", "tone": "차분",
            "viewer_needs": "권태기를 넘기는 법",
            "evidence": [{"quote": "만나도 각자 휴대폰만 봐요", "source": "transcript"}]}
GOOD = ("'만나도 각자 휴대폰만 봐요'라는 말이 오래 남네요. 요즘 운명원 연애 사주 잘 본다던데 "
        "저도 한번 가 보려고요.")


def _with_fake_llm(monkeypatch, llm):
    """main()이 만드는 서비스에 가짜 LLM을 끼운다(AI·인터넷 없이)."""
    llm.model = "fake"
    llm.close = lambda: None
    real = C.build_services

    def build(settings, **kwargs):
        services = real(settings, llm_transport=httpx.MockTransport(_llm_off), **kwargs)
        if services.llm is not None:
            services.llm.close()
        services.llm = llm
        return services

    monkeypatch.setattr(C, "build_services", build)


def _record_temp(monkeypatch) -> list[Path]:
    made: list[Path] = []
    real = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        made.append(Path(real(*args, **kwargs)))
        return str(made[-1])

    monkeypatch.setattr(C.tempfile, "mkdtemp", mkdtemp)
    return made


def _db_copy(tmp_path: Path) -> Path:
    src = tmp_path / "app-copy.sqlite3"
    db.init_db(src)
    return src


def test_db_path_writes_result_files_and_cleans_up(tmp_path, fake_llm, monkeypatch, capsys):
    vid = E.load_contexts(CONTEXTS, limit=1)[0]["video_id"]
    _with_fake_llm(monkeypatch, fake_llm([ANALYSIS, {"body": GOOD, "used_quote":
                                                     "만나도 각자 휴대폰만 봐요",
                                                     "mood": "공감형", "wish": "궁합"}]))
    made = _record_temp(monkeypatch)
    src = _db_copy(tmp_path)
    before = src.read_bytes()
    out_json, out_md = tmp_path / "out" / "r.json", tmp_path / "out" / "r.md"

    assert C.main(["--ai", "ollama", "--db", str(src), "--fixtures", vid, "-d", "1",
                   "--out-json", str(out_json), "--out-md", str(out_md)]) == 0

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["finished"] is True and data["model"] == "fake"
    assert [v["video_id"] for v in data["videos"]] == [vid]
    assert GOOD in data["videos"][0]["drafts"][0]["body"]  # 앞에 광고 표기가 붙는다
    assert GOOD in out_md.read_text(encoding="utf-8")
    assert src.read_bytes() == before  # 원본 DB는 읽기만
    # 서비스·DB 연결을 닫고 나와 임시 폴더가 지워진다(Windows에서 파일이 잡혀 있으면 남는다)
    assert made and not made[0].exists()
    assert "경고" not in capsys.readouterr().err
    assert not list(out_json.parent.glob("*.part"))


def test_json_keeps_finished_videos_when_a_later_video_crashes(tmp_path, fake_llm, monkeypatch):
    two = E.load_contexts(CONTEXTS, limit=2)
    assert len(two) == 2
    ids = [c["video_id"] for c in two]
    # 첫 영상만 응답을 준비한다 → 둘째 영상에서 가짜 LLM이 AssertionError로 죽는다
    _with_fake_llm(monkeypatch, fake_llm([ANALYSIS, {"body": GOOD, "used_quote":
                                                     "만나도 각자 휴대폰만 봐요",
                                                     "mood": "공감형", "wish": "궁합"}]))
    made = _record_temp(monkeypatch)
    out_json = tmp_path / "partial.json"

    with pytest.raises(AssertionError):
        C.main(["--ai", "ollama", "--db", str(_db_copy(tmp_path)), "--fixtures", ",".join(ids),
                "-d", "1", "--out-json", str(out_json)])

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["finished"] is False
    assert [v["video_id"] for v in data["videos"]] == [ids[0]]
    assert GOOD in data["videos"][0]["drafts"][0]["body"]  # 앞에 광고 표기가 붙는다
    assert made and not made[0].exists()  # 죽어도 닫고 지운다


def test_temp_cleanup_failure_is_one_warning(tmp_path, monkeypatch, capsys):
    def boom(path):
        raise PermissionError(32, "다른 프로세스가 파일을 사용 중")

    monkeypatch.setattr(C.shutil, "rmtree", boom)
    C.remove_temp(tmp_path / "x")
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and err.startswith("경고: 임시 폴더를 지우지 못했습니다")


# ------------------------------------------------ 2026-11-18 지표(지시서 7절)


def test_stats_count_endings_fact_copies_kinds_and_reviews():
    fact = "운명원은 연애 사주를 잘 봐주는 곳으로 유명하다"
    rows = [
        ("[광고] 장거리 얘기 남 일 같지 않네요. 운명원 연애 사주 잘 본다던데 인연 언제 오는지 보러 "
         "가야겠어요", "passed", [], "인연이 오는 때"),
        ("[광고] 연락 문제로 싸웠다니. 운명원이 연애 사주 잘 본다니까 궁합 보러 가야겠어요",
         "rewritten", ["어색"], "궁합"),
        (f"[광고] 권태기라니. {fact}. 저도 왜 매번 이러는지 알아보러 가려고요", "flagged",
         ["x"], "반복되는 연애 패턴"),
        ("[광고] 짝사랑이라니. 운명원 가서 내 짝 어디 있는지 물어봐야지", "error", [], ""),
    ]
    videos = [{"video_id": "v", "drafts": [
        {"body": b, "chars": len(b), "passed": True, "first_passed": i != 1,
         "attempts": 2 if i == 1 else 1, "seconds": 2.0, "review": st, "review_first": first,
         "wish_kind": kind, "voice": "존댓말", "heard": "요즘 자주 들어서",
         "retry_reasons": [["V1: 길이"]] if i == 1 else []}
        for i, (b, st, first, kind) in enumerate(rows)]}]
    stats = C._stats(videos, [fact])
    assert stats["첫 시도 규칙 검사 통과"] == "3/4"
    assert stats["첫 검수 통과"] == "1/4"
    assert stats["검수 고쳐 써서 통과 · 고쳐도 남음 · 못 함"] == "1 · 1 · 1"
    assert stats["끝말이 글자까지 같은 초안"] == "2"  # 「보러 가야겠어요」 둘
    assert stats["운명원 소개를 거의 그대로 옮김"] == "1"
    kinds = stats["알고 싶은 것 갈래"]
    assert "기타" not in kinds and "(검수 안 함) 1" in kinds
    assert stats["다시 쓰게 만든 까닭"] == "AI 검수 2, V1 1"
    assert stats["말 높임"] == "존댓말 4"


def test_ending_is_the_last_two_words_without_laughs():
    assert C.ending("[광고] 저도 한번 보러 가야겠네요ㅋㅋ") == "보러 가야겠네요"
    assert C.ending("가 봐야지...") == "가 봐야지"
