"""초안 다듬기 검사(C1 다듬기, 2026-11-17 대표 지시 「초안 더 다듬고」).

규칙 검사(V1~V14)를 통과한 초안 가운데 **읽기에 어색한 꼴**을 코드로 찾는다. 이 검사는 승인을
막지 않는다 — 모델이 쓴 초안을 한 번 더 쓰게 하는 까닭(다시 쓸 차례가 남았을 때)과 다듬기
단계(`prompts.polish_user`)에 넘길 「남은 문제」로만 쓴다. 사람이 고친 글에는 쓰지 않는다.

- S1 길이: 전체 110자를 넘음(목표 80~110자, 한도 40~120자는 V1 그대로)
- S2 바람에 핵심 말: 운명원 문장(바람)에 영상의 핵심 말을 끼움
  (「내짝 찾기 언제 되는지 궁금해지네요」). 「저도」 뒤 가 보겠다는 말 앞의 짧은 까닭
  (`prompts.intent_reason`, 「저도 읽씹이 무서워서 조만간 한번 가보려구요」)은 빼고 본다(2026-11-18)
- S3 띄어쓰기·말꼴: 「이유여쭤보고」처럼 붙여 씀, 「없었네라는 말에」처럼 말끝에 바로 「라는」
- S4 같은 영상 앞 초안과 비슷함: [다른 댓글 만들기]가 거의 같은 글을 내지 않게
- S6 늘어진 문장: 「~는데/인데」로 이은 문장에 운명원의 「~던데」를 또 이음(2026-11-17)
- S7 평판 없음: 운명원을 꺼내는 대목에 무엇을 잘하는지(연애 사주를 잘 본다·잘 봐준다·잘 맞는다·
  유명하다)가 없음(2026-11-17 대표: 운명원은 「연애 사주 잘 봐주는 곳으로 유명한 곳」)
- S8 본보기 연달아: 대표의 본보기(`prompts.BRAND_MODELS`)의 꺼내는 말을 그대로 옮긴 초안이 바로
  앞 초안과 같은 본보기를 옮김(2026-11-17 대표: 「그대로 베끼지 말고 이 결로」)
- S10 까닭 되풀이: 운명원 대목 ⑤의 까닭(`prompts.intent_reason`)이 앞서 보인 초안(다른 영상
  포함)의 까닭과 같음 — 글이 같거나, 끝 낱말을 뺀 낱말이 둘 이상 겹침(「호감 기준 알고 싶어」·
  「호감 기준이 궁금해서」), 2026-11-18 기획 담당: 「저도 썸이 답답해서」가 영상 셋에서 나옴
- S9 끝난 말에 조사: 영상 속 말을 따옴표 없이 그대로 옮기고 끝난 말(~거예요·~거야·~잖아·
  ~어요)에 조사를 바로 붙임(「말하는 거예요가 답인가 봐」「헤어지자는 거야부터」 → 「말하는 게」
  「헤어지자는 말부터」, 2026-11-18 기획 담당이 초안 28개에서 찾음)
- S11 잇는 문장·까닭 없음: 영상 반응 바로 뒤에 운명원이 나오고 ⑤의 까닭도 없음 — 공식처럼
  읽힌다(2026-11-18 기획 담당, 대표 승인). 반응과 운명원 사이에 인연·타이밍·때·궁합·맞는 사람
  쪽으로 넘어가는 잇는 한 문장(`prompts.bridge_sentence`)이나 ⑤의 까닭 가운데 하나는 있어야 한다.
  **모델이 쓴 초안에만** 본다(`need_bridge`) — 사람이 고친 글과 대표 본보기 10개는 그대로 둔다.
- S12 잇는 문장 되풀이: 잇는 문장이 앞서 보인 초안(다른 영상 포함)이나 프롬프트의 좋은 예의 잇는
  문장과 같거나 거의 같음(맞춤법을 지우고 70% 넘게 같음)
- S14 잇는 문장의 새 평판(2026-11-18): 운명원 문장 바로 앞 문장(잇는 문장 자리)에 설정에 없는
  운명원 평판·사례(`validator.invented_repute` — 예약·방송·연예인·가격·위치·경력·적중률·구체 사례·
  남이 받아 본 결과). 운명원 대목 자체는 규칙 검사 V14가 막는다
- S5 영상 사연을 내 것으로: 영상 속 **숫자**(「3년 사귄」「2년째」「석 달」)를 영상 얘기라는
  표지(「~대요」「~라니」「~다는 말에」) 없이 내 일처럼 옮긴 문장. 비슷한 처지라고 말하는 것
  (「완전 제 얘기네요」「저도 비슷해서」「우리 사이」)은 시청자 말투로 둔다(기획 담당 2026-11-17:
  막을 것은 사연 복사와 내 일이 될 수 없는 것 둘뿐 — 뒤의 것은 프롬프트로만 막는다).

S3는 「~인지 한번 가 봐야겠어요」(「언제인지 한번 가 봐야겠네요」)와 「제 연애 운세 한번 가
봐야겠네요」도 잡는다 — 「가 봐야겠다」는 물음도, 운세·시기 같은 목적어도 받지 못한다
(「~인지 한번 보고 싶다」, 「궁금해서 다음에 한번 가 봐야겠네요」로). 1~7회차 초안 112개에
대 보니 목적어 꼴은 「연애 운세 한번 가 봐야겠네요」 2개만 걸렸다.

문구는 규칙 검사처럼 「무엇이 걸렸고 — 어떻게 고치면 되는지」 한 줄이다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from difflib import SequenceMatcher

from app.analysis.validator import (
    V14_REPUTE,
    contains_key_phrase,
    hashtags,
    invented_repute,
    normalize,
    strip_hashtags,
)
from app.llm.prompts import bridge_sentence, copied_model, fold, intent_reason, with_i

SOFT_MAX_TOTAL = 110
# 1~5회차 실제 초안: 다른 영상 초안끼리 가장 닮은 것이 0.55, 같은 영상 두 초안은 0.18~0.67,
# 대표가 본 영상의 두 초안은 0.94였다. 다른 영상 글만큼도 다르지 않으면 다시 쓰게 한다.
SAME_VIDEO_SIMILARITY = 0.55
# S12: 잇는 문장끼리 이만큼 같으면 되풀이로 본다(「결국 타이밍 문제인가 싶네요」·「결국 타이밍
# 문제인가 싶어요」)
SAME_BRIDGE_SIMILARITY = 0.7

_SPLIT = re.compile(r"[.!?…\n]+|(?<=[ㄱ-ㅎㅏ-ㅣ])\s+")
_WISH = re.compile(
    r"싶|봐야|볼까|가\s?볼|궁금|물어보|여쭤|알아보|보려고|볼래|해\s?볼|받아\s?보|할까|보자|좋겠|"
    r"려[고구]|생각|방문|상담"
)
# 붙여 쓴 꼴: 앞말에 바로 붙은 「여쭤보·물어보·알아보」(되물어보·캐물어보는 한 낱말)
_GLUED = re.compile(r"(?<=[가-힣])(?<![되캐])(여쭤보|물어보|알아보)")
# 말끝(~네)에 바로 붙은 「라는 말」: 「없었네라는 말에」 → 「없었다는 말에」
_NE_RANEUN = re.compile(r"[가-힣]*네라는\s?말")
# 「~인지/~는지/~ㄹ지 (한번) 가 봐야겠다」: 물음 뒤에 「가 봐야」(사이에 「궁금해서」 등이 있으면
# 괜찮다)
_ASK_GO = re.compile(r"[가-힣]+지\s+((?:[가-힣]+\s+){0,3}?)가\s?봐야")
_ASK_GO_OK = re.compile(r"궁금|싶어서|알고\s?싶|물어보러|보러|여쭈러")
# 「운세·시기 (한번) 가 봐야겠다」: 가는 곳이 아닌 것을 「가 봐야」의 목적어로
_THING_GO = re.compile(
    r"(?<![가-힣])(?:연애\s?)?(?:운세|연애운|시기|타이밍|궁합|사주|앞날|미래|결말)(?:을|를|도)?\s+"
    r"(?:(?:한번|한\s번|다음에|꼭|언제)\s+)*가\s?봐야"
)
# 영상 속 숫자: 「3년」「2년째」「6개월」「석 달」「두 달」
_NUMBER = re.compile(
    r"\d+\s?(?:년|개월|달|주|살|번|일|시간|명|월|차)|"
    r"(?<![가-힣])(?:한|두|세|석|넉|네|다섯|여섯|일곱|여덟|아홉|열)\s?달(?![라려리콤])"
)
# 영상 얘기로 받는 표지(이게 있으면 숫자를 옮겨도 내 일이 아니다)
_ABOUT_VIDEO = re.compile(
    r"말에|말이|대요|래요|댔|랬|대\b|래\b|라니|다니|다는|라는|던데|다고|라고|사연|영상|댓글|"
    r"그분|이분|(?:거|걸|글|영상|댓글|사연|얘기|말)\s?보니|듣고|봤는데|셨|시죠|시네|으시"
)
# S9(2026-11-18): 끝난 말 + 조사가 띄어 쓰지 않고 바로 붙은 꼴. 끝말은 모음으로 끝나 조사는
# 「가·를·부터·는·도·만·랑·처럼·보다·까지」만 본다. 「요가 수업」(앞에 끝말 없음), 「~해요. 가끔」
# 「~해요 가끔」(띄어 씀), 「~다가」「~는데도」「~다는」「~다고」(끝말 목록에 없음), 「'…거예요'가」
# (따옴표로 묶음), 「좋아요가 많다」(누르는 단추 이름)는 걸리지 않는다.
_ENDED_PARTICLE = re.compile(
    r"(?<![좋싫])"
    r"(?:거예요|거에요|예요|에요|어요|아요|여요|해요|네요|래요|대요|게요|잖아요|거든요|거야|잖아)"
    r"(?:가|를|부터|는|도|만|랑|처럼|보다|까지)(?=[\s.,!?…~]|$)"
)
# S7(2026-11-17, 대표): 운명원 페르소나 = 「연애 사주 잘 봐주는 곳으로 유명한 곳」(과제 원문).
# 꺼내는 대목(운명원 문장 + 바로 앞 문장)에 잘한다는 평판이 없으면 다시 쓰게 한다.
# 2026-11-18: 과제 설정을 다른 말로 옮긴 평판(소문·얘기가 많음·추천·후기가 많음)도 평판으로 본다
_REPUTATION = re.compile(
    r"잘\s?(?:보|봐|본|볼|맞)|유명|평이\s?좋|평판이\s?좋|용하|정확|소문|추천|"
    r"(?:얘기|이야기|말|후기)(?:가|이)\s?많"
)
# S6(2026-11-17, PDF 대조): 「~는데/인데」로 이은 문장에 브랜드의 「~던데」를 또 이음 —
# 「저도 고민인데 운명원 … 잘 본다던데 …」, 「동아리 선배라서 더 조심스러운데 요즘 운명원 얘기 자주
# 보이던데」. 지난 초안 156개(1~8회차·C1 전)에 대 보니 1개만 걸렸고 그 글은 「늘어진다」로 짚었던
# 어색한 글이었다. 승인은 막지 않고 다시 쓸 차례가 남았을 때만 다시 쓰게 한다.
# Codex 1회차(16개)에서 「고민인데, 요즘 운명원 … 보이던데」처럼 쉼표 찍은 꼴이 5개 — 쉼표도 본다.
_NEUNDE_DEONDE = re.compile(
    r"(?<!던)(?:는데|인데|은데|운데|한데),?\s(?:(?!던데)[^.!?…])*?던데"
)


def _neunde_before_brand(sentence: str, brand: str) -> bool:
    """S6: 「~는데」가 운명원 **앞**에 있고 운명원 뒤 「~던데」까지 한 문장으로 이어졌는가.

    「친구가 운명원에서 연애 사주 봤는데 잘 맞는다고 하던데」처럼 운명원을 꺼낸 뒤의 「~는데」는
    남이 본 얘기를 전하는 한 덩어리라 늘어진 문장으로 보지 않는다(2026-11-17 대표 예).
    """
    if not brand or brand not in sentence:
        return False
    at = sentence.index(brand)
    return any(m.start() < at for m in _NEUNDE_DEONDE.finditer(sentence))


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if s.strip()]


def _body(text: str, disclosure: str) -> str:
    rest = text.strip()
    if disclosure and rest.startswith(disclosure):
        rest = rest[len(disclosure):].strip()
    return rest


def wish_part(text: str, brand: str) -> str:
    """운명원을 꺼낸 뒤의 바람 대목: 브랜드 문장의 브랜드 뒤쪽(+ 바람이 없으면 다음 문장)."""
    sentences = _sentences(text)
    for i, s in enumerate(sentences):
        if brand and brand in s:
            part = s.split(brand, 1)[1]
            if not _WISH.search(part) and i + 1 < len(sentences):
                part += " " + sentences[i + 1]
            return part
    return ""


def hearsay_mark(text: str, brand: str) -> str:
    """운명원 문장에 쓴 꺼내는 말 표지: 잘한다는 말부터 들은 얘기 꼴의 낱말 끝까지
    (「잘 본다고 하던데」「정확하다는 얘기」). 없으면 빈 글(맞춤법 차이는 견줄 때 `fold`로
    지운다)."""
    for s in _sentences(text):
        if brand and brand in s:
            m = V14_REPUTE.search(s)
            if not m:
                return ""
            rest = re.match(r"[가-힣]*", s[m.end():])
            return m.group(0) + (rest.group(0) if rest else "")
    return ""


def has_reputation(text: str, brand: str) -> bool:
    """운명원 문장(또는 바로 앞 문장)에 잘한다는 평판이 있는가. 운명원이 없으면 참(V5가 본다)."""
    sentences = _sentences(text)
    spots = [i for i, s in enumerate(sentences) if brand and brand in s]
    if not spots:
        return True
    return any(
        _REPUTATION.search(sentences[i]) or (i > 0 and _REPUTATION.search(sentences[i - 1]))
        for i in spots
    )


def _before_brand(text: str, brand: str) -> str:
    """운명원이 처음 나오는 문장의 바로 앞 문장(첫 문장이면 빈 글) — 잇는 문장 자리."""
    sentences = _sentences(text)
    at = next((i for i, s in enumerate(sentences) if brand and brand in s), -1)
    return sentences[at - 1] if at >= 2 else ""


def used_phrases(text: str, key_phrases: Sequence[str]) -> list[str]:
    return [k for k in key_phrases if k and contains_key_phrase(text, k)]


def style_issues(
    text: str,
    *,
    brand: str,
    disclosure: str,
    key_phrases: Sequence[str] = (),
    earlier: Sequence[str] = (),
    context: str = "",
    max_total: int = SOFT_MAX_TOTAL,
    last_shown: str = "",
    used_reasons: Sequence[str] = (),
    need_bridge: bool = False,
    used_bridges: Sequence[str] = (),
) -> list[str]:
    """다시 쓰게 할 까닭들(없으면 빈 목록).

    `earlier`: 같은 영상에 앞서 쓴 초안 글. `context`: 영상 자료 글(S5 숫자 대조, 없으면 S5를
    보지 않는다). `last_shown`: 바로 앞에 사람에게 보인 초안(S8, 없으면 보지 않는다).
    `used_reasons`: 앞서 보인 초안들의 ⑤ 까닭(S10, 없으면 보지 않는다).
    `need_bridge`: 참이면 잇는 문장·까닭이 둘 다 없는 글을 S11로 잡는다(모델이 쓴 초안만).
    `used_bridges`: 앞서 보인 초안·좋은 예의 잇는 문장(S12, 없으면 보지 않는다).
    `context`는 S13(해시태그로만 있는 낱말을 댓글에 씀, 2026-11-18)에도 쓴다.
    """
    issues: list[str] = []
    body = _body(text, disclosure)
    if len(text) > max_total:
        issues.append(
            f"S1 길이: {len(text)}자로 깁니다 — {max_total}자 안으로 줄이세요(② 내 처지 한마디나 "
            "④ 마무리는 빼도 됩니다)"
        )
    wish = wish_part(body, brand)
    reason = intent_reason(body, brand)
    if reason:  # ⑤의 까닭(「저도 읽씹이 무서워서 …」)은 고민·핵심 말에서 온다(2026-11-18)
        wish = wish.replace(reason, " ")
    stuffed = [
        k for k in key_phrases
        if k and len(normalize(k)) >= 2 and contains_key_phrase(wish, k)
    ]
    if stuffed:
        shown = ", ".join(f"'{k}'" for k in stuffed[:2])
        issues.append(
            f"S2 바람에 핵심 말: {brand} 뒤의 바람에 핵심 말 {shown}을(를) 끼웠습니다 — 핵심 말은 "
            "영상 반응에만 쓰고, 바람은 '나도 언제 짝 만나는지', '이 사람이랑 이어질지'처럼 쉬운 "
            "내 말로 쓰세요"
        )
    glued = [m.group(0) for m in _GLUED.finditer(body)]
    spans = [body[max(0, m.start() - 2) : m.end() + 1] for m in _GLUED.finditer(body)]
    if glued:
        issues.append(
            f"S3 띄어쓰기·말꼴: '{spans[0]}'처럼 붙여 썼습니다 — '이유 물어보고'처럼 띄어 쓰세요"
        )
    ne = _NE_RANEUN.search(body)
    if ne:
        issues.append(
            f"S3 띄어쓰기·말꼴: '{ne.group(0)}'은 어색합니다 — '~했다는 말에'처럼 고치세요"
        )
    ask = next((m for m in _ASK_GO.finditer(body) if not _ASK_GO_OK.search(m.group(1))), None)
    if ask:
        issues.append(
            f"S3 띄어쓰기·말꼴: '{ask.group(0)}'은 앞뒤가 안 맞습니다 — '~인지 한번 보고 싶다'로 "
            "쓰거나, 물음 없이 '다음에 한번 가 봐야겠네요'로 쓰세요"
        )
    thing = _THING_GO.search(body)
    if thing:
        issues.append(
            f"S3 띄어쓰기·말꼴: '{thing.group(0)}'은 어색합니다 — 운세·시기는 가는 곳이 아니니 "
            "'연애 운세 한번 보고 싶다'나 '다음에 한번 가 봐야겠네요'로 쓰세요"
        )
    if brand and not has_reputation(body, brand):
        issues.append(
            f"S7 평판 없음: {brand}을(를) 꺼내는 말에 무엇을 잘하는지가 없습니다 — '{brand} 연애 "
            f"사주 잘 본다던데', '친구가 {brand}에서 연애 사주 봤는데 잘 맞는다고 하던데'처럼 연애 "
            "사주를 잘 본다는 평판으로 꺼내세요"
        )
    doubled = next((s for s in _sentences(body) if _neunde_before_brand(s, brand)), "")
    if doubled:
        issues.append(
            f"S6 늘어진 문장: '~는데/~인데' 뒤에 {brand}의 '~던데'를 또 이었습니다 — 앞을 끊어 "
            f"'…고민이에요. 요즘 {brand} …던데'처럼 새 문장으로 꺼내세요"
        )
    model = copied_model(body)
    if model >= 0 and last_shown and copied_model(last_shown) == model:
        issues.append(
            f"S8 본보기 연달아: {brand}을(를) 꺼내는 말이 바로 앞 초안처럼 본보기 {model + 1}번을 "
            "그대로 옮겼습니다 — 때·세기 말·들은 얘기 꼴을 바꿔 다른 말로 꺼내세요"
        )
    old_reason = repeated_reason(reason, used_reasons)
    if old_reason:
        issues.append(
            f"S10 까닭 되풀이: '{reason}'은 앞 초안의 까닭('{old_reason}')과 같습니다 — 이 영상의 "
            "고민에서 다른 까닭을 내 말로 쓰거나, 까닭 없이 맺으세요"
        )
    bridge = bridge_sentence(body, brand) if brand else ""
    if need_bridge and brand and brand in body and not bridge and not reason:
        issues.append(
            f"S11 잇는 문장 없음: 영상 반응 바로 뒤에 {with_i(brand)} 나와 공식처럼 "
            "읽힙니다 — 사이에 이 고민이 결국 인연·타이밍·때·궁합·맞는 사람의 문제일지도 "
            "모른다는 짧은 혼잣말 한 문장을 넣거나, 끝말의 '저도' 뒤에 이 영상 고민에서 온 짧은 "
            "까닭을 넣으세요(영상 반응은 짧게)"
        )
    # S14(2026-11-18): 운명원 문장 바로 앞 문장(첫 문장=영상 반응 다음, 잇는 문장 자리)에 설정에
    # 없는 운명원 평판·사례 — 운명원 대목은 V14가 본다. 잇는 말이 없어도 그 자리면 본다
    spot = _before_brand(body, brand)
    invented = invented_repute(spot) if spot else None
    if invented:
        issues.append(
            f"S14 잇는 문장의 새 평판: '{spot}'에 설정에 없는 말"
            f"({invented[0]}: '{invented[1]}')이 있습니다 — 잇는 문장은 영상 얘기에서 사주 "
            "쪽으로 넘어가는 말만 쓰세요"
        )
    old_bridge = repeated_bridge(bridge, used_bridges)
    if old_bridge:
        issues.append(
            f"S12 잇는 문장 되풀이: '{bridge}'은 앞서 쓴 잇는 문장('{old_bridge}')과 거의 같습니다 "
            "— 이 영상 고민에 맞는 다른 말로 쓰세요"
        )
    tag = hashtag_word(body, context)
    if tag:
        issues.append(
            f"S13 해시태그 낱말: '{tag}'은 영상의 해시태그(#{tag})에만 있는 말입니다 — 해시태그 "
            "낱말은 댓글에 쓰지 말고 영상 속 사연·인기 댓글의 말로 쓰세요"
        )
    ended = _ENDED_PARTICLE.search(body)
    if ended:
        start = max(body.rfind(" ", 0, ended.start()) + 1, 0)
        issues.append(
            f"S9 끝난 말에 조사: '{body[start:ended.end()]}'처럼 끝난 말에 조사를 바로 붙였습니다 "
            "— 영상 속 말은 '~라는 말', '~하는 게', '~다니'처럼 내 말로 바꿔 쓰세요"
            "('헤어지자는 거야부터' → '헤어지자는 말부터')"
        )
    copied = _copied_number(body, context, brand)
    if copied:
        issues.append(
            f"S5 영상 사연을 내 것으로: '{copied}'는 영상 속 사연의 숫자입니다 — 내 일처럼 "
            "옮기지 말고 '저도 오래 만나다 보니'처럼 숫자 없이 내 말로 쓰거나, '~했대요'처럼 "
            "영상 얘기로 받으세요(비슷한 처지라고 말하는 것은 괜찮습니다)"
        )
    issues += _same_video(body, brand=brand, disclosure=disclosure, key_phrases=key_phrases,
                          earlier=earlier)
    return issues


_PARTICLE_TAIL = re.compile(r"(?:이랑|하고|이|가|을|를|은|는|도|의|랑|에|로)$")


def _reason_stems(reason: str) -> set[str]:
    """까닭의 낱말(끝 낱말 「답답해서·궁금해서·때문에」는 빼고, 뒤 조사를 뗀 두 글자 이상)."""
    words = reason.split()[:-1]
    stems = set()
    for w in words:
        stem = _PARTICLE_TAIL.sub("", w) if len(w) > 2 else w
        if len(stem) >= 2:
            stems.add(stem)
    return stems


def repeated_reason(reason: str, used: Sequence[str]) -> str:
    """S10: `reason`과 같은 앞 까닭(없으면 빈 글). 글이 같거나 낱말이 둘 이상 겹치면 같다."""
    if not reason:
        return ""
    mine, stems = fold(reason), _reason_stems(reason)
    for old in used:
        if not old:
            continue
        if fold(old) == mine or len(stems & _reason_stems(old)) >= 2:
            return old
    return ""


def hashtag_word(body: str, context: str) -> str:
    """S13(2026-11-18): 글에 든 해시태그 낱말(자료에서 #태그로만 나오는 3자 이상 말, 없으면 빈 글).

    「#인팁특징」이 핵심 말로 뽑혀 댓글에 「인팁특징」이 들어갔다. 태그로도 있지만 제목·자막·댓글에
    그대로도 있는 말(「#연애」와 「연애」)은 걸지 않는다."""
    if not context:
        return ""
    plain = normalize(strip_hashtags(context))
    body_n = normalize(body)
    for tag in hashtags(context, limit=40):
        n = normalize(tag)
        if len(n) >= 3 and n not in plain and n in body_n:
            return tag
    return ""


def repeated_bridge(bridge: str, used: Sequence[str]) -> str:
    """S12: `bridge`와 같거나 거의 같은 앞 잇는 문장(없으면 빈 글)."""
    if not bridge:
        return ""
    mine = fold(bridge)
    for old in used:
        if not old:
            continue
        theirs = fold(old)
        if theirs == mine or SequenceMatcher(None, mine, theirs).ratio() > SAME_BRIDGE_SIMILARITY:
            return old
    return ""


def _copied_number(body: str, context: str, brand: str) -> str:
    """영상 자료에 있는 숫자를 영상 얘기라는 표지 없이 쓴 문장의 그 숫자(없으면 빈 글)."""
    if not context:
        return ""
    ctx = normalize(context)
    parts: list[str] = []
    for s in _sentences(body):
        if brand and brand in s:
            # 운명원을 꺼내는 들은 얘기(「~던데」)는 영상 얘기 표지가 아니다. 그 뒤 「저도 …」의
            # 까닭(⑤, 2026-11-18)은 따로 본다: 「저도 3년 만난 사람 때문에」
            before, after = s.split(brand, 1)
            parts.append(before)
            mine = re.search(r"(?<![가-힣])(?:저도|나도)\s.*", after)
            if mine:
                parts.append(mine.group(0))
        else:
            parts.append(s)
    for s in parts:
        if _ABOUT_VIDEO.search(s):
            continue
        for m in _NUMBER.finditer(s):
            if s[m.end():].lstrip().startswith(("이면", "면")):
                continue  # 「3년이면 진짜 식은 건지」: 영상 속 숫자를 두고 하는 말
            if normalize(m.group(0)) in ctx:
                return m.group(0)
    return ""


def _same_video(
    body: str, *, brand: str, disclosure: str, key_phrases: Sequence[str], earlier: Sequence[str]
) -> list[str]:
    def flat(t: str) -> str:
        rest = _body(t, disclosure)
        return normalize(rest.replace(brand, " ") if brand else rest)

    mine = flat(body)
    mark = hearsay_mark(body, brand)
    phrases = set(used_phrases(body, key_phrases))
    many = len([k for k in key_phrases if k]) >= 2
    for old in earlier:
        old_body = _body(old, disclosure)
        ratio = SequenceMatcher(None, mine, flat(old), autojunk=False).ratio()
        if ratio >= SAME_VIDEO_SIMILARITY:
            return [
                f"S4 앞 초안과 비슷함: 같은 영상의 앞 초안과 {round(ratio * 100)}% 같습니다 — 짚는 "
                "장면·핵심 말·말투·운명원 꺼내는 말·끝말을 바꿔 다른 글로 쓰세요"
            ]
        if mark and fold(mark) == fold(hearsay_mark(old_body, brand)):
            return [
                f"S4 앞 초안과 비슷함: 운명원을 앞 초안과 같은 말('{mark}')로 꺼냈습니다 — 다른 "
                "들은 얘기로 꺼내세요"
            ]
        if many and phrases and phrases == set(used_phrases(old_body, key_phrases)):
            shown = ", ".join(f"'{k}'" for k in sorted(phrases))
            return [
                f"S4 앞 초안과 비슷함: 앞 초안과 같은 핵심 말({shown})만 썼습니다 — 다른 핵심 말로 "
                "다른 장면을 짚으세요"
            ]
    return []
