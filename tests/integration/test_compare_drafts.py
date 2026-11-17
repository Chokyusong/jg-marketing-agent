"""초안 전후 비교 스크립트(scripts/compare_drafts.py)를 가짜 LLM으로 돌린다(AI·인터넷 없이).

- 글 쓰는 AI는 앱과 같은 `build_llm(settings)`로 고른다(`llm.active`·모델만 바꾼다).
- 영상마다 초안 N개, 처음 통과한 초안 승인, 시도별 글·다시 쓰기 까닭을 남긴다.
- 표: 초안 전문(전·후 나란히), 지표, 다듬기 검사로 남은 수.
"""

from pathlib import Path

import httpx
import pytest

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
    good_a = (f"'{quote_a}'라는 말이 오래 남네요. 운명원 연애 사주 잘 본다던데 "
              "한번 보고 싶어요.")
    good_b = ("같은 식당, 같은 카페에서 데이트가 끝난다는 말에 공감했어요. "
              "요즘 운명원 얘기 자주 보이던데 연애 흐름을 짚어 보고 싶네요.")
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
