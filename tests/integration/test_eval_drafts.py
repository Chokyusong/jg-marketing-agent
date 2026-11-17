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
    # 실제 데이터 보정으로 협찬 위주 자료(06)가 더해졌다. 연애 주제 다섯은 그대로(01~05)
    items = E.load_contexts(CONTEXTS)
    assert len(items) == 6
    love = [c for c in items if not c.get("foreign_products")]
    assert len(love) == 5
    assert len({c["video_id"] for c in items}) == 6
    assert len({c["title"] for c in items}) == 6
    for c in love:
        assert len(c["video_id"]) == 11
        assert c["transcript"].count("\n") >= 4 and len(c["comments"]) >= 3 and c["description"]


def test_sponsored_fixture_is_mostly_ads_without_transcript():
    ctx = json.loads((CONTEXTS / "06_sponsored.json").read_text(encoding="utf-8"))
    assert len(ctx["video_id"]) == 11 and not ctx.get("transcript")
    assert "연애" in ctx["title"]
    products = ctx["foreign_products"]
    assert products and all(p in ctx["description"] for p in products)
    ads = [c for c in ctx["comments"] if any(p in c for p in products)]
    assert len(ads) * 2 == len(ctx["comments"])  # 댓글 절반이 이벤트 응모 글


def _sponsored_run(fake_llm, tmp_db_path, responses):
    contexts = [c for c in E.load_contexts(CONTEXTS) if c["video_id"] == "EvalCtx0006"]
    llm = fake_llm(responses)
    llm.model = "fake"
    settings = E.eval_settings("fake", tmp_db_path)
    services = build_services(settings, transport=E.youtube_transport(contexts),
                              llm_transport=httpx.MockTransport(_llm_off))
    services.llm = llm
    try:
        E.prepare(services, contexts)
        result = E.ModelResult(model="fake")
        E.run_contexts(services, contexts, drafts_per_context=1, result=result, log=lambda s: None)
    finally:
        services.llm = None
        services.close()
    return result, llm


def test_eval_counts_drafts_that_push_another_product(tmp_db_path, fake_llm):
    quote = "기념일마다 서운한데 말하면 쪼잔해 보일까 봐"
    analysis = {"has_love_concern": True, "reason": "기념일 서운함 댓글", "topic": "기념일",
                "concern": "기념일을 잊는 애인에게 서운함", "tone": "상담",
                "viewer_needs": "서운함 말하기",
                "evidence": [{"quote": quote, "source": "comment"}]}
    bad = (f"'{quote}'라는 말에 공감해요. 운명원에서 상담받기 전에 쾌속장 화이바톡으로 "
           "속부터 편하게 해 보세요.")
    result, llm = _sponsored_run(fake_llm, tmp_db_path, [analysis] + [
        {"body": bad, "used_quote": quote, "tone_label": "공감형"}] * 3)
    # 자막이 없어 「광고·협찬 글이 섞여 있을 수 있다」는 안내가 분석 프롬프트에 붙었다
    assert "설명란과 댓글에는 광고·협찬" in llm.calls[0]["kwargs"]["user"]
    row = result.drafts[0]
    assert row.foreign_product == "화이바톡"
    assert result.summary()["foreign_product_drafts"] == 1
    table = E.markdown([result], contexts=1, drafts=1)
    assert "남의 상품 권함(화이바톡)" in table
    assert "| `fake` | EvalCtx0006 | 기념일을 잊는 애인에게 서운함 | " in table


def test_eval_counts_no_love_concern_as_a_stop(tmp_db_path, fake_llm):
    none = {"has_love_concern": False, "reason": "협찬 상품 이벤트 글뿐", "topic": "",
            "concern": "", "tone": "", "viewer_needs": "", "evidence": []}
    result, llm = _sponsored_run(fake_llm, tmp_db_path, [none])
    assert len(llm.calls) == 1  # 초안을 쓰게 하지 않았다
    assert result.analyses == [{"video_id": "EvalCtx0006", "no_concern": True,
                                "reason": "협찬 상품 이벤트 글뿐"}]
    assert result.drafts[0].no_concern and not result.drafts[0].foreign_product
    summary = result.summary()
    assert summary["no_concern_stops"] == 1 and summary["foreign_product_drafts"] == 0
    assert "| `fake` | EvalCtx0006 | 연애 고민 없음 · 멈춤 | 0/1 | 0 |" in E.markdown(
        [result], contexts=1, drafts=1)


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
    # C1: 자료를 13자 이상 이어서 옮기지 않는다(V13)
    good_b = ("같은 식당, 같은 카페에서 데이트가 끝난다는 말에 공감했어요. "
              "운명원 연애 사주로 흐름을 짚어 보고 싶네요.")  # 굳은 틀(셈 확인용)
    llm = fake_llm([analysis,
                    {"body": "연애 사주 상담을 받아 보세요.", "used_quote": "",
                     "tone_label": "조언형"},
                    {"body": good_a, "used_quote": quote_a, "tone_label": "공감형"},
                    {"body": good_b, "used_quote": quote_b, "tone_label": "혼잣말형"}])
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
