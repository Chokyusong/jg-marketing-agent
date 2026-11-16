"""모델 비교 스크립트(scripts/eval_drafts.py)를 가짜 LLM으로 끝까지 돌린다(Ollama·인터넷 없이).

가상 맥락(tests/fixtures/contexts/)이 가짜 YouTube 응답으로 바뀌어 앱의 실제 흐름에 들어가는지,
표와 모델 고르는 규칙이 맞는지 본다.
"""

import json
from pathlib import Path

import httpx

from app.api.deps import build_services
from scripts import eval_drafts as E

CONTEXTS = Path(__file__).resolve().parent.parent / "fixtures" / "contexts"


def _llm_off(request):
    raise httpx.ConnectError("Ollama 꺼짐(테스트)", request=request)


def test_fixture_contexts_are_five_distinct_topics():
    items = E.load_contexts(CONTEXTS)
    assert len(items) == 5
    assert len({c["video_id"] for c in items}) == 5
    assert len({c["title"] for c in items}) == 5
    for c in items:
        assert len(c["video_id"]) == 11
        assert c["transcript"].count("\n") >= 4 and len(c["comments"]) >= 3 and c["description"]


def test_eval_runs_the_real_pipeline_with_fake_llm(tmp_db_path, fake_llm):
    contexts = E.load_contexts(CONTEXTS, limit=1)
    ctx = contexts[0]
    quote_a = "만나도 각자 휴대폰만 봐요"
    quote_b = "같은 식당, 같은 카페에서 끝나요"
    analysis = {"topic": "권태기", "concern": "설렘이 사라진 3년 연애", "tone": "차분",
                "viewer_needs": "권태기를 넘기는 법",
                "evidence": [{"quote": quote_a, "source": "transcript"},
                             {"quote": quote_b, "source": "transcript"},
                             {"quote": "매일 꽃을 사 왔대요", "source": "transcript"}]}
    good_a = f"'{quote_a}'라는 말이 오래 남네요. 운명원에서 연애 사주 상담을 받아 보세요."
    good_b = f"'{quote_b}'라는 말에 공감했어요. 운명원의 연애 사주 상담으로 흐름을 짚어 보세요."
    llm = fake_llm([analysis,
                    {"body": "연애 사주 상담을 받아 보세요.", "used_quote": "",
                     "tone_label": "조언형"},
                    {"body": good_a, "used_quote": quote_a, "tone_label": "공감형"},
                    {"body": good_b, "used_quote": quote_b, "tone_label": "공감형"}])
    llm.model = "fake"

    settings = E.eval_settings("fake", tmp_db_path)
    services = build_services(settings, transport=E.youtube_transport(contexts),
                              llm_transport=httpx.MockTransport(_llm_off))
    services.llm = llm
    try:
        E.prepare(services, contexts)
        result = E.ModelResult(model="fake")
        E.run_contexts(services, contexts, drafts_per_context=2, result=result,
                       log=lambda s: None, approve_first=True)
    finally:
        services.llm = None  # 가짜 LLM에는 close가 없다
        services.close()

    assert result.analyses[0]["dropped"] == 1  # 지어낸 근거를 버렸다
    first, second = result.drafts
    assert (first.attempts, first.passed, first.first_passed) == (2, True, False)
    assert (second.attempts, second.passed, second.first_passed) == (1, True, True)
    assert first.quote == quote_a and second.quote == quote_b  # 두 번째는 다른 근거
    assert first.body.startswith("[광고] ")
    assert result.rate("first_passed") == 0.5 and result.rate("passed") == 1.0
    # 자막을 붙여 넣은 맥락이 분석 프롬프트에 들어갔다
    assert ctx["title"] in llm.calls[0]["kwargs"]["user"]
    assert "[자막 · 붙여 넣은 자막]" in llm.calls[0]["kwargs"]["user"]

    table = E.markdown([result], contexts=1, drafts=2)
    assert "| `fake` | 2 | 50% | 100% |" in table
    assert good_a in table
    # 영상마다 처음 통과한 초안을 승인했다(다음 영상의 「이미 쓴 권유 문장」이 된다)
    assert first.approved and not second.approved
    assert services.drafts is not None
    # 권유 문장 다양성: 서로 다른 것 2개, 굳은 틀(흐름을 짚어) 1개, V12 0개, 승인 1개
    stats = result.closing_stats()
    assert stats == {"distinct_closings": 2, "stock_closings": 1, "v12_failed": 0, "approved": 1}
    assert "| `fake` | 2/2 | 1 | 0 | 1 |" in table
    assert "통과 · 승인" in table
    json.dumps(result.summary(), ensure_ascii=False)


def test_pick_model_rule():
    def made(name, passed, first, secs):
        r = E.ModelResult(model=name)
        for p, f in zip(passed, first, strict=True):
            r.drafts.append(E.DraftRow("v", "t", 1, passed=p, first_passed=f, seconds=secs,
                                       attempts=1))
        return r

    a = made("a", [True, True], [False, False], 1.0)
    b = made("b", [True, True], [True, False], 9.0)
    c = made("c", [True, False], [True, True], 0.5)
    assert E.pick_model([a, b, c]).model == "b"  # 3번 안 통과율 → 첫 시도 통과율
    d = made("d", [True, True], [True, False], 2.0)
    assert E.pick_model([b, d]).model == "d"  # 둘 다 같으면 빠른 쪽
    broken = E.ModelResult(model="x", error="llm_down")
    assert E.pick_model([broken]) is None
