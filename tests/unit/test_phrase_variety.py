"""영상마다 다르게(2026-11-17, PDF 대조) — 같은 표현 되풀이 줄이기.

Codex(`gpt-5.6-luna`) 영상 8개 × 초안 2개에서 「자꾸 눈에 띄던데」 4번, 「나도 한번 볼까
싶다」 4번이 나왔다. 코드가 권하는 꺼내는 말·끝말 목록이 짧았고, 오래전 글까지 센 횟수만 보아
드물게 쓴 말 하나가 영상마다 「가장 덜 쓴 것」으로 남았다.

- 목록을 넉넉히(모두 V14·V8·V10·S3에 안 걸리는지 여기서 본다), 최근 글에 쓴 것을 먼저 피한다.
- 목록은 권유일 뿐(프롬프트에 「목록에 없는 자연스러운 말도 된다」).
- S6: 「~는데/인데」 뒤에 운명원의 「~던데」를 또 이은 문장은 다시 쓰게 한다(승인은 막지 않음).
- 분석: 설명란에만 있는 채널 홍보·방송 일정 안내는 근거·핵심 말에서 뺀다.
"""

from __future__ import annotations

import random

import pytest
from test_context_fit import make_context

from app.analysis import style as S
from app.analysis.analyzer import check_evidence, check_key_phrases, is_channel_promo
from app.analysis.context import search_text
from app.analysis.validator import ValidatorRules, validate
from app.llm import prompts as P

RULES = ValidatorRules(min_chars=40, max_chars=120, brand="운명원", disclosure="[광고]")
FACTS = ["연애 사주 상담을 하는 곳"]
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"


def _check(text: str):
    return validate(
        text, context_text=CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        evidence_quote="하루에 한 번 연락", key_phrases=["하루에 한 번 연락"],
    )


def test_lists_are_long_enough_and_distinct():
    assert len(P.HEARSAY_LINES) >= 12
    assert len(P.WISH_ENDINGS) >= 12
    assert len({m for _, m in P.HEARSAY_LINES}) == len(P.HEARSAY_LINES)
    assert len(set(P.WISH_ENDINGS)) == len(P.WISH_ENDINGS)
    # 과제 예시와 대표가 든 꼴이 들어 있다
    hearsay = [P.fill_hearsay(t, "운명원") for t, _ in P.HEARSAY_LINES]
    assert "운명원 연애 사주 잘 본다던데" in hearsay
    assert "요새 운명원 연애 사주 그렇게 잘 본다고 하던데" in hearsay
    # 한 줄의 표시가 다른 줄에 들어 있으면 그 줄을 쓸 때 둘 다 쓴 것으로 세진다
    for lead in hearsay:
        hits = [m for _, m in P.HEARSAY_LINES if m in lead]
        assert len(hits) == 1, (lead, hits)
    assert "한번 보고 싶다" in P.WISH_ENDINGS and "다음에 한번 가 봐야겠네요" in P.WISH_ENDINGS
    assert "여쭤보고 싶네요" not in P.WISH_ENDINGS


@pytest.mark.parametrize("line", [t for t, _ in P.HEARSAY_LINES])
def test_every_hearsay_line_passes_the_rules(line):
    lead = P.fill_hearsay(line, "운명원")
    text = f"[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. {lead} 나도 한번 보고 싶다."
    result = _check(text)
    failed = [c.code for c in result.checks if not c.passed]
    assert failed == [], (lead, failed)
    assert S.hearsay_mark(text, "운명원"), lead  # S4가 같은 꺼내는 말을 알아본다


@pytest.mark.parametrize("ending", P.WISH_ENDINGS)
def test_every_ending_passes_the_rules_and_style(ending):
    text = (f"[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "
            f"운명원 연애 사주 잘 본다던데 {ending}.")
    result = _check(text)
    failed = [c.code for c in result.checks if not c.passed]
    assert failed == [], (ending, failed)
    assert S.style_issues(text, brand="운명원", disclosure="[광고]") == [], ending


def test_recent_use_is_avoided_before_old_counts():
    """오래전 글에 많이 쓴 말보다, 최근 글에 쓴 말을 먼저 피한다."""
    old = ["[광고] 운명원 연애 사주 잘 본다던데 한번 보고 싶다."] * 5
    # 2026-11-17 페르소나: 예전 「요즘 운명원 얘기가 자꾸 눈에 띄던데」(평판 없음)를 목록에서 뺐다
    recent = ["[광고] 운명원 연애 사주 잘 본다고 입소문 났던데 나도 한번 볼까 싶다."]
    # 방금(최근 6개 안) 한 번 쓴 말이 오래전에 다섯 번 쓴 말보다 뒤로 간다
    filler = ["…"] * (P.RECENT_TEXTS - 1)
    picks = P.hearsay_choices("운명원", recent + filler + old, n=len(P.HEARSAY_LINES))
    assert picks[-2:] == ["운명원 연애 사주 잘 본다던데", "운명원 연애 사주 잘 본다고 입소문 "
        "났던데"]
    # 최근 6개 글 밖으로 밀려나면 전체 횟수로만 본다(다섯 번 쓴 말이 맨 뒤)
    used = ["…"] * P.RECENT_TEXTS + recent + old  # 최신이 앞
    picks = P.hearsay_choices("운명원", used, n=len(P.HEARSAY_LINES))
    assert picks[-2:] == ["운명원 연애 사주 잘 본다고 입소문 났던데", "운명원 연애 사주 잘 "
        "본다던데"]
    endings = P.ending_choices(recent, n=len(P.WISH_ENDINGS))
    assert endings[-1] == "나도 한번 볼까 싶다"


def test_ending_without_pronoun_still_counts_as_used():
    """「나도」 없이 쓴 「…인지 한번 볼까 싶다」도 「나도 한번 볼까 싶다」를 쓴 것으로 센다."""
    assert "한번 볼까 싶" in P.WISH_MARKERS and "한번 봐 볼까 봐" in P.WISH_MARKERS
    used = ["[광고] 다들 운명원에서 연애운 본다길래 다시 이어질지 한번 볼까 싶다."]
    endings = P.ending_choices(used, n=len(P.WISH_ENDINGS))
    assert endings[-1] == "나도 한번 볼까 싶다"


def test_system_prompt_does_not_seed_one_ending():
    """임무 문장이 「한번 볼까 싶어지게」였더니 모델이 그 말을 끝말로 되풀이했다(Codex 6/16)."""
    system = P.draft_system(brand="운명원", disclosure="[광고]", facts=FACTS)
    assert "볼까' 싶어지게" not in system
    assert "운명원 연애 사주에 관심이 가게 한다" in system


def test_eight_videos_in_a_row_do_not_repeat_the_same_lead():
    """모델이 첫 권유를 고른다고 치면 8개 영상에서 같은 말이 되풀이되지 않는다."""
    used: list[str] = []
    leads, endings = [], []
    for _ in range(8):
        lead = P.hearsay_choices("운명원", used, n=3)[0]
        end = P.ending_choices(used, n=3)[0]
        leads.append(lead)
        endings.append(end)
        used.insert(0, f"[광고] 영상 얘기. {lead} {end}.")
    assert len(set(leads)) == 8 and len(set(endings)) == 8


def test_empty_history_picks_differ_by_seed():
    """2026-11-17(대표 「잘 보기로 유명하다던데 이것만 나와?」): 기록이 하나도 없는 새 PC에서도
    영상마다 다른 말을 권한다 — 횟수가 같으면 목록 순서가 아니라 무작위. 씨앗이 같으면 같은 답."""
    firsts = {P.hearsay_choices("운명원", [], n=3, rng=random.Random(s))[0] for s in range(12)}
    ends = {P.ending_choices([], n=3, rng=random.Random(seed))[0] for seed in range(12)}
    assert len(firsts) >= 5 and len(ends) >= 5
    a = P.hearsay_choices("운명원", [], n=3, rng=random.Random(7))
    assert a == P.hearsay_choices("운명원", [], n=3, rng=random.Random(7))
    assert a != P.hearsay_choices("운명원", [], n=3, rng=random.Random(8))
    # 기본(씨앗 없음)도 무작위: 여러 번 부르면 처음 권하는 말이 한 가지로 굳지 않는다
    assert len({P.hearsay_choices("운명원", [])[0] for _ in range(40)}) > 1


def test_draft_user_says_lists_are_only_suggestions():
    text = P.draft_user(
        analysis={"topic": "t", "concern": "c"}, quote="q", source="comment", min_body=35,
        max_body=115, brand="운명원", hearsay=["운명원 연애 사주 잘 본다던데"],
        endings=["궁금해지네요"],
    )
    assert "목록에 없는 자연스러운 들은 얘기로 써도 된다" in text
    assert "목록에 없는 자연스러운 말도 된다" in text
    assert "'저도 고민인데 운명원 잘 본다던데 …' ✗" in text
    system = P.draft_system(brand="운명원", disclosure="[광고]", facts=FACTS)
    assert "목록은 권유이지 틀이 아니다" in system
    assert "'나도 한번 볼까 싶다'" not in system  # 고정 예가 굳은 끝말이 되지 않게


# ---------------------------------------------------------------- S6


@pytest.mark.parametrize("text", [
    "[광고] 저도 요즘 이 고민인데 운명원 연애 사주 잘 본다던데 한번 보고 싶다.",
    # (2026-11-17 페르소나: 아래 셋의 꺼내는 말에 평판을 넣었다 — 평판이 없으면 S7도 걸린다)
    "[광고] 거절당하면 동아리 못 간다는 말에 진짜 공감되네요...ㅠ 동아리 선배라서 더 조심스러운데 "
    "요즘 운명원 연애 사주 잘 본다던데 내 마음도 한번 물어보고 싶어요",
    "[광고] 연락 문제는 늘 어려운데 주변에서 운명원 연애 사주 잘 본다고들 하던데 나도 한번 볼까 "
    "싶다.",
    # Codex 1회차: 쉼표를 찍어도 같은 꼴
    "[광고] 저도 맞는 사람을 만날 수 있을지 늘 고민인데, 운명원이 연애 사주를 잘 봐준다고 하던데 "
    "결혼까지 이어질 인연인지 물어보고 싶어요.",
])
def test_s6_neunde_then_deonde_in_one_sentence(text):
    found = S.style_issues(text, brand="운명원", disclosure="[광고]")
    assert [i[:2] for i in found] == ["S6"], found
    assert "새 문장으로 꺼내세요" in found[0]


@pytest.mark.parametrize("text", [
    # 끊어 쓰면 괜찮다
    "[광고] 저도 요즘 이 고민이에요. 운명원 연애 사주 잘 본다던데 한번 보고 싶다.",
    # 「~던데」만, 「~는데」가 운명원 문장 밖에
    "[광고] 연락이 뜸해지는데 괜히 불안하네요. 운명원이 연애 쪽으로 유명하다던데 궁금해지네.",
    # 「들었는데」처럼 운명원을 꺼내는 말 자체가 「~는데」(뒤에 「~던데」 없음)
    "[광고] 남 일 같지 않네요. 운명원 연애 사주 잘 맞춘다는 얘기 들었는데 한번 보고 싶다.",
    # 「~던데」 뒤의 「~는데」는 순서가 달라 늘어지지 않는다
    "[광고] 남 일 같지 않네요. 운명원 연애 사주 잘 본다던데 나도 궁금한데 한번 보고 싶다.",
])
def test_s6_allows_split_or_single_connective(text):
    assert [i[:2] for i in S.style_issues(text, brand="운명원", disclosure="[광고]")] == []


# ---------------------------------------------------------------- 분석: 설명란 채널 홍보


PROMO_DESC = ("매주 수요일 밤 연애상담 라이브를 합니다. 사연 보내주세요! "
              "오늘은 하루에 한 번 연락하는 커플의 고민을 다뤘습니다.")


def test_channel_promo_in_description_is_not_evidence_or_key_phrase():
    ctx = make_context(description=PROMO_DESC, transcript="하루에 한 번 연락하자고 해서 싸웠어요")
    text = search_text(ctx)
    assert is_channel_promo("연애상담 라이브", ctx)
    assert is_channel_promo("사연 보내주세요", ctx)
    assert not is_channel_promo("하루에 한 번 연락", ctx)  # 라이브 같은 말이 없다
    kept, dropped = check_evidence(
        [{"quote": "매주 수요일 밤 연애상담 라이브를 합니다", "source": "description"},
         {"quote": "하루에 한 번 연락하자고 해서 싸웠어요", "source": "transcript"}],
        ctx, text,
    )
    assert [e.quote for e in kept] == ["하루에 한 번 연락하자고 해서 싸웠어요"]
    assert dropped == ["매주 수요일 밤 연애상담 라이브를 합니다"]
    phrases, lost = check_key_phrases(["연애상담 라이브", "하루에 한 번 연락"], text, ctx)
    assert phrases == ["하루에 한 번 연락"] and lost == ["연애상담 라이브"]
    # 자료를 안 주면(예전 호출) 예전 그대로
    assert "연애상담 라이브" in check_key_phrases(["연애상담 라이브"], text)[0]


def test_same_words_in_the_transcript_are_kept():
    """자막에도 나오는 말이면 영상 얘기일 수 있다(「매주 만나는데」 같은 사연)."""
    ctx = make_context(description="매주 만나는 커플 이야기",
                       transcript="저희는 매주 만나는 커플인데요")
    assert not is_channel_promo("매주 만나는 커플", ctx)
