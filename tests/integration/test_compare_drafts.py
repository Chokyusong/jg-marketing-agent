"""초안 전후 비교 스크립트(scripts/compare_drafts.py)를 가짜 LLM으로 돌린다(AI·인터넷 없이).

- 글 쓰는 AI는 앱과 같은 `build_llm(settings)`로 고른다(`llm.active`·모델만 바꾼다).
- 영상마다 초안 N개, 처음 통과한 초안 승인, 시도별 글·다시 쓰기 까닭을 남긴다.
- 표: 초안 전문(전·후 나란히), 지표, 다듬기 검사로 남은 수.
"""

import json
import random
import re
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
              "저도 한번 가 보려고요.")
    good_b = ("같은 식당, 같은 카페에서 데이트가 끝난다는 말에 공감했어요. "
              "요즘 운명원 연애 사주 잘 본다고 하던데 연애 흐름을 짚어 보러 저도 한번 가 "
              "보려고요.")
    llm = fake_llm([analysis,
                    {"body": "연애 사주 상담을 받아 보세요.", "used_quote": "",
                     "tone_label": "조언형"},
                    {"body": good_a, "used_quote": quote_a, "tone_label": "공감형"},
                    {"body": good_b, "used_quote": quote_b, "tone_label": "혼잣말형"}])
    llm.model = "fake"
    settings = C.make_settings("ollama", tmp_db_path, model="fake", environ={})
    services = build_services(settings, transport=E.youtube_transport(contexts),
                              llm_transport=httpx.MockTransport(_llm_off))
    services.llm = llm
    try:
        E.prepare(services, contexts)
        videos = C.run(services, [vid], drafts_per_video=2,
                       titles={vid: contexts[0]["title"]}, log=lambda s: None)
        ctx_text = services.context.search_text(services.context.current(vid))
        rules = services.drafts.rules
    finally:
        services.llm = None
        services.close()

    (row,) = videos
    first, second = row["drafts"]
    assert (first["attempts"], first["passed"], first["first_passed"]) == (2, True, False)
    assert first["retry_reasons"] and first["retry_reasons"][0]  # 다시 쓰게 한 까닭이 남는다
    assert [a["body"] for a in first["run"]["attempts"]][-1] == first["body"]
    assert second["quote"] == quote_b and second["attempts"] == 1

    # 전·후 나란히: 예전 결과의 같은 영상 초안 옆에 놓는다
    before = [{"video_id": vid, "drafts": [{"n": 1, "body": "[광고] 예전 글", "chars": 9,
                                            "passed": True, "first_passed": True,
                                            "attempts": 1, "seconds": 1.0}]}]
    table = C.markdown_table(videos, before=before, labels=("7회차", "8회차"), brand=rules.brand,
                             disclosure=rules.disclosure, contexts={vid: ctx_text})
    assert "| 영상 | # | 7회차 | 8회차 |" in table
    assert "[광고] 예전 글 (9자 · 통과 · 1번째)" in table
    assert f"{first['body']} ({first['chars']}자 · 통과 · 2번째)" in table
    assert "| 3번 안 통과 | 1/1 | 2/2 |" in table
    assert "| 시도 1·2·3번 | 1 · 0 · 0 | 1 · 1 · 0 |" in table
    assert "다듬기 검사로 남은 초안 수" in table and "8회차 다시 쓰게 만든 까닭: V" in table
    # 한 열만
    alone = C.markdown_table(videos, brand=rules.brand, disclosure=rules.disclosure)
    assert "| 영상 | # | 후 |" in alone and "예전 글" not in alone


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
                                                     "tone_label": "공감형"}]))
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
                                                     "tone_label": "공감형"}]))
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


# ------------------------------------------------ 2026-11-17 꺼내는 말·끝말이 영상마다 흩어지는지

# 2026-11-18: 권유 목록 대신 코드가 정해 준 조각 줄(「이번 초안의 운명원 대목: … 이어 쓰면:
# '꺼내는 말, 저도 끝말'」)
PIECES_HEAD = "이번 초안의 운명원 대목:"


def _assigned(prompt: str) -> tuple[str, str]:
    line = next(x for x in prompt.splitlines() if x.startswith(PIECES_HEAD))
    joined = line.split("이어 쓰면: '", 1)[1].split("'", 1)[0]
    lead, ending = re.split(r"[,.] 저도 ", joined, maxsplit=1)
    return lead, "저도 " + ending


class FirstChoiceLLM:
    """정해 준 꺼내는 말·끝말을 그대로 쓰는 가짜 AI(실제 모델이 조각을 따른다고 칠 때).
    2026-11-18 전에는 권유 목록의 첫 번째를 썼다."""

    model = "fake-first-choice"

    def __init__(self, contexts):
        self.contexts = contexts
        self.leads: list[str] = []
        self.endings: list[str] = []

    def close(self):
        pass

    def generate_json(self, *, system, user, schema, **kwargs):
        ctx = max((c for c in self.contexts if c["comments"][0] in user),
                  key=lambda c: len(c["comments"][0]))
        quote = ctx["comments"][0]
        if "evidence" in schema.get("properties", {}):
            return {"topic": "연애 고민", "concern": "이 관계를 계속 가도 될까", "tone": "차분",
                    "viewer_needs": "고민을 덜고 싶다", "is_love": True,
                    "evidence": [{"quote": quote, "source": "comment"}], "key_phrases": []}
        lead, ending = _assigned(user)
        self.leads.append(lead)
        self.endings.append(ending)
        joint = ". " if lead.endswith(("요", "여")) else ", "  # 끝말은 「저도 …」로 시작한다
        return {"body": f"댓글 보니 남 일 같지 않네요. {lead}{joint}{ending}.",
                "used_quote": quote, "tone_label": "공감형"}


def six_contexts() -> list[dict]:
    """연애 고민이 있는 가상 영상 5개(06은 협찬 영상이라 일부러 고민이 없다) + 01을 바꾼 하나."""
    loaded = E.load_contexts(CONTEXTS)
    contexts = [c for c in loaded if c["video_id"] != "EvalCtx0006"][:5]
    extra = json.loads(json.dumps(contexts[0], ensure_ascii=False))
    extra["video_id"] = "EvalCtx0099"
    extra["title"] = "권태기 사연 둘째 이야기"
    extra["comments"] = ["둘째 사연도 " + c for c in extra["comments"]]
    return contexts + [extra]


def spread(seed: int) -> tuple[list[str], list[str], list[dict]]:
    contexts = six_contexts()
    llm = FirstChoiceLLM(contexts)
    with tempfile.TemporaryDirectory() as tmp:
        settings = C.make_settings("ollama", Path(tmp) / "app.sqlite3", model="fake", environ={})
        services = build_services(settings, transport=E.youtube_transport(contexts),
                                  llm_transport=httpx.MockTransport(_llm_off))
        services.llm = llm
        services.drafts.rng = random.Random(seed)
        try:
            E.prepare(services, contexts)
            videos = C.run(services, [c["video_id"] for c in contexts], drafts_per_video=1,
                           log=lambda s: None, approve=False)
            with db.session(settings.db_path) as conn:
                statuses = {r["status"] for r in conn.execute("SELECT status FROM drafts")}
        finally:
            services.llm = None
            services.close()
    assert statuses == {"draft"}  # 하나도 승인하지 않았다
    # 영상마다 본문에 들어간 꺼내는 말·끝말(겹치면 긴 것)
    def found(options: list[str], body: str) -> str:
        return max((x for x in set(options) if x in body), key=len)

    bodies = [v["drafts"][0]["body"] for v in videos]
    return ([found(llm.leads, b) for b in bodies], [found(llm.endings, b) for b in bodies],
            videos)


def test_six_videos_without_approval_spread_leads_and_endings():
    """대표(2026-11-17): 초안을 보기만 하고 게시하지 않으면 「잘 보기로 유명하다던데」만 나왔다.
    보인 초안 전부를 「이미 쓴 글」로 세면 6개 영상에서 꺼내는 말·끝말이 5가지 이상."""
    leads, endings, videos = spread(seed=11)
    assert len(videos) == 6
    assert len(set(leads)) >= 5, leads
    assert len(set(endings)) >= 5, endings


def test_seed_changes_the_first_suggestion_on_an_empty_history():
    first_a = spread(seed=1)[0][0]
    others = {spread(seed=s)[0][0] for s in (2, 3, 4)}
    assert others - {first_a}, (first_a, others)


def test_stats_count_bridges_reasons_and_ai_review():
    """2026-11-18: 잇는 문장·까닭·잇는 문장 되풀이와 AI 검수 결과를 센다."""
    lead = "요즘 운명원이 연애사주를 잘 본다고 하더라구요. "
    bodies = [
        ("[광고] 연락 문제로 싸웠다니. 결국 타이밍 문제인가 싶네요. " + lead + "저도 가보려구요.",
         "passed", []),
        ("[광고] 기대치 차이라니. 결국 타이밍 문제인가 싶어요. " + lead + "저도 가보려구요.",
         "rewritten", ["x"]),
        ("[광고] 장거리라니. " + lead + "저도 연락 문제로 조만간 가보려구요.", "flagged", ["y"]),
        ("[광고] 장거리라니. " + lead + "저도 가보려구요.", "error", []),
    ]
    videos = [{"video_id": "v", "drafts": [
        {"body": b, "chars": len(b), "passed": True, "first_passed": True, "attempts": 1,
         "seconds": 2.0, "review": st, "review_first": first} for b, st, first in bodies]}]
    stats = C._stats(videos)
    assert stats["잇는 문장 있음"] == "2/4" and stats["까닭 있음"] == "1/4"
    assert stats["잇는 문장 되풀이"] == "1"
    assert stats["AI 검수 거짓(처음)"] == "2" and stats["AI 검수 고쳐 써서 통과"] == "1"
    assert stats["AI 검수 고쳐도 남음"] == "1" and stats["AI 검수 못 함"] == "1"
    assert stats["초안 1개 평균 시간"] == "2.0초"


def test_review_before_and_after_are_listed_side_by_side_with_times():
    """2026-11-18 검수 기록: 다시 쓰기를 한 초안만 고치기 전·문제·고친 뒤·결과·시간을 나란히."""
    base = {"chars": 60, "passed": True, "first_passed": True, "attempts": 1, "seconds": 3.0}
    videos = [{"video_id": "v", "title": "영상", "drafts": [
        {**base, "n": 1, "body": "[광고] 고친 뒤", "review": "rewritten", "review_first": ["어색"],
         "review_before": "[광고] 고치기 전", "review_after": "[광고] 고친 뒤", "review_kept": True,
         "review_ms": 1200, "rewrite_ms": 2400},
        {**base, "n": 2, "body": "[광고] 앞 초안", "review": "error", "review_first": ["z"],
         "review_before": "[광고] 앞 초안", "review_after": "[광고] 버린 글", "review_kept": False,
         "review_ms": 800, "rewrite_ms": 2000},
        {**base, "n": 3, "body": "[광고] 그대로", "review": "passed", "review_first": [],
         "review_before": "", "review_after": "", "review_kept": None, "review_ms": 600,
         "rewrite_ms": 0},
    ]}]
    lines = C.review_trace_lines(videos)
    rows = [ln for ln in lines if ln.startswith("| 영상 |") and ln.split("|")[2].strip().isdigit()]
    assert len(rows) == 2
    assert "[광고] 고치기 전 | 어색 | [광고] 고친 뒤 | 씀 · rewritten | 1.2초 · 2.4초" in rows[0]
    assert "버림(앞 초안 씀) · error" in rows[1]
    stats = C._stats(videos)
    assert stats["다시 쓴 글 버림(앞 초안 씀)"] == "1"
    assert stats["검수 1번 평균 시간(초안당 합)"] == "0.9초"
    assert stats["다시 쓰기 평균 시간"] == "2.2초(2개)"
