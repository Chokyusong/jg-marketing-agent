"""이야기처럼 쓰기 프롬프트(2026-11-18 대표 결정, `comment.writer: story`).

2026-11-18 대표 「이렇게 해보자」(붙여 준 최종 시스템 프롬프트): AI가 댓글 **전체를 한 번에** 쓴다.
코드가 장면·처지·궁금한 것·추임새 같은 문장 조각을 따로 만들게 하지 않는다(그것도 조각 강제였다).
고민 한 줄(concern)만 본문보다 먼저 정리한다. 글자 수는 코드가 설정값으로 검사하고, 넘거나 모자라면
다시 쓰게 한다. 본보기는 과제 예시 하나(흐름만 참고). 따옴표는 본문에서 코드가 지운다(대표).
끝말 예시 문구는 넣지 않는다(하나만 있으면 모든 댓글이 그 말로 끝났다). 이미 쓴 댓글도 쓰는 AI에게
보여 주지 않는다(drafter — 똑같은 글은 코드가 뒤에서 본다).

2026-11-18 대표 지시서(「생각이 발전하는 과정」): 댓글은 영상 속 구체적인 상황 → 반응 →
거기서 자라난 생각·궁금증 → 운명원 연애 사주로 이어지는 한 줄기 이야기다. 기준 한 문장 —
「운명원을 언급하기 직전의 생각이 왜 영상 내용에서 나왔는지 설명할 수 없다면, 그 댓글은 다시
작성하라.」 쓰기 전에 속으로 답해 볼 물음 셋을 주되 답을 칸으로 받지 않는다(글은 통째로).
가상의 시청자 관점과 영상에 맞는 가상의 연애 고민·처지는 AI가 정해 써도 된다. 누가 얘기해 줬다는
경위(「친구한테 듣기로」)도 된다. 금지는 운명원을 직접 이용했다는 허위 후기 하나다.

2026-11-18 대표(테라 초안 22개를 읽고): 거의 다 「영상 반응 → 저도 궁금해요 → 운명원에서 보고
싶어요」 한 공식이었고, 사주를 꺼내려고 지어낸 궁금증(소통 방법·표현 방식·용기 낼 시점을 사주로
알아보겠다)이 섞였다. 그 공식으로 밀던 문구 — 속으로 답할 물음 셋, 「이유 없이 바로 넘어가지
않는다」, 「궁금 → 궁합」 방향 예 하나 — 를 덜어 내고, 감상을 먼저 풀고 그 생각이 닿는 자리에서
운명원을 꺼내며 그 길은 영상마다 다르다는 것과 지어낸 궁금증 금지로 바꿨다. 문장 조각·말투 순환은
더하지 않았다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.analysis.validator import ASSIGNMENT_SAMPLE
from app.llm import prompts
from app.llm.prompts import SOURCE_LABELS, TONE_LABELS

MAX_SHOWN = 6  # 「이미 쓴 글」로 보여 줄 앞 초안 수
QUOTE_MARKS = "'\"‘’“”「」『』"

# 길이로 걸려 다시 쓸 때만 덧붙이는 말(2026-11-18 대표: 120자는 과제 조건. 줄이면서 생각이 이어지는
# 부분이 먼저 잘렸다 — 처음 쓸 때는 아무것도 정하지 않고, 줄일 때 남길 것만 알린다)
SHORTEN_LINE = (
    "영상 속 구체적인 장면, 거기서 자라난 생각, {brand} 연애 사주는 지우지 말고 꾸미는 말·되풀이·"
    "영상 내용을 길게 옮긴 곳을 덜어 줄인다."
)

# 길이로 세 번 다 걸렸을 때 한 번씩 더 쓰게 하는 말(차례대로). 구조는 정하지 않고 길이만 알린다
DROP_LINES = (
    "",
    "앞서 쓴 글이 모두 길었다 — 댓글 전체를 더 짧게 다시 쓴다.",
    "그래도 길었다 — 꼭 필요한 말만 남겨 짧은 댓글로 다시 쓴다.",
)


# 처음 쓰는 글의 권장 길이(2026-11-18 대표: 120자 한도인데 첫 글이 모두 127~184자였다 — 모델은
# 글자 수를 세지 못해 상한을 목표로 삼으면 넘친다). 기준은 설정 40~120자이고, 상한의 0.75~0.875를
# 5자 단위로 「권장」으로만 준다(강제 범위가 아니다)
TARGET_LOW = 0.75
TARGET_HIGH = 0.875


def story_target(*, min_body: int, max_body: int) -> tuple[int, int]:
    """본문 권장 길이(공백 포함). 120자 한도면 90~105자. 하한은 설정 하한 밑으로 내리지 않는다."""
    hi = max(min_body, round(max_body * TARGET_HIGH / 5) * 5)
    lo = min(hi, max(min_body, round(max_body * TARGET_LOW / 5) * 5))
    return lo, hi



def story_system(
    *, brand: str, disclosure: str, facts: Sequence[str], sample: str = "",
    min_body: int = 40, max_body: int = 120,
) -> str:
    """이야기 방식의 시스템 글 — 대표가 붙여 준 「댓글 생성 시스템 프롬프트」에 대표 지시서(생각이
    발전하는 과정)를 넣은 것. 목표 길이는 `story_target`(본문 기준, 표기 켬/끔과 상관없다)."""
    lo, hi = story_target(min_body=min_body, max_body=max_body)
    fact_lines = "\n".join(f"- {f}" for f in facts) or (
        f"- {brand}은 연애 사주를 잘 봐주는 곳으로 유명하다"
    )
    best = sample or ASSIGNMENT_SAMPLE
    # 본보기 길이를 따라 쓰지 않게(과제 예시는 139자) — 글자 수는 코드가 센다
    longer = (f"이 예시는 {len(best)}자로 우리 한도보다 길다. 생각이 이어지는 방식만 참고하고 "
              "길이는 따라 하지 않는다.\n") if len(best) > hi else ""
    return (
        "너는 유튜브 연애 영상을 이해하고, 그 영상에 어울리는 자연스러운 한국어 댓글을 작성하는 "
        "AI다.\n"
        "\n"
        "## 목표\n"
        "영상의 내용을 정확히 이해하고, 영상을 본 시청자의 관점에서 공감과 생각이 자연스럽게 "
        "이어지는 댓글을 작성한다.\n"
        f"댓글을 읽는 사람이 {brand}에서 연애 사주를 보고 싶어지도록 하되, 영상 이야기와 "
        "관계없이 브랜드를 억지로 끼워 넣지 않는다.\n"
        "\n"
        "## 작성 방법\n"
        "1. 먼저 영상 자막, 제목·설명, 인기 댓글을 읽고 영상이 다루는 핵심 연애 고민을 한 줄로 "
        "정리한다.\n"
        "2. 영상에 실제로 등장하는 구체적인 장면이나 말을 하나 이상 짚는다. 영상 속 말은 "
        "따옴표로 옮기지 않고 내 말로 풀어 쓴다. 자막이 없다면 제목·설명 등에서 확인되는 내용을 "
        "사용한다. 인기 댓글의 사연은 영상에서 직접 말한 내용처럼 표현하지 않는다.\n"
        "3. 댓글은 생각이 발전하는 한 줄기 이야기다. 영상에 대한 감상·공감·생각을 먼저 "
        f"자연스럽게 풀고, 그 생각이 닿는 자리에서 {brand} 연애 사주를 꺼낸다. 그 길은 영상마다 "
        "다르다(「궁금해졌다」가 아니어도 된다 — 내 연애가 떠올랐다, 인연이라는 게 있나 싶다, "
        "나라면 어떨까). 이것은 생각의 흐름이지 문장 구조가 아니다 — 문장 수와 나누는 방식은 "
        "정하지 않고, 글은 통째로 쓴다.\n"
        "4. 사주를 꺼내려고 궁금증을 지어내지 않는다. 사주로 볼 일이 아닌 것(대화 요령, 말하는 "
        "법, 용기 낼 시점 같은 실용적인 답)을 사주에서 알아보겠다고 쓰지 않는다. 자연스럽게 "
        "이어지는 지점이 인연·궁합·연애운·때 쪽이면 그 얘기로, 아니면 영상의 고민에 대한 내 "
        f"생각을 말한 뒤 {brand}을 담백하게 꺼낸다.\n"
        "5. 말투·관점·문장 수·잇는 말·끝말은 자유다. 실제 시청자처럼 ㅋㅋ·ㅠㅠ·^^ 같은 이모티콘도 "
        "써도 된다.\n"
        "6. 가상의 시청자 관점이나 영상에 맞는 가상의 연애 고민·처지를 정해 써도 된다. "
        "감정·생각·궁금증·가정(저라도 불안할 것 같아요)도 내 것으로 써도 된다.\n"
        f"7. {brand}은 「~라던데」 같은 들은 평판으로 꺼내고(요새·요즘·친구한테 듣기로 같은 말을 "
        f"붙여도 된다), 앞의 생각이 {brand} "
        "연애 사주를 보고 싶은 마음으로 이어지게 맺는다. 제공된 브랜드 사실 범위 안에서 "
        "표현하고, "
        f"{brand}을 직접 이용하거나 상담받은 것처럼 지어낸 후기는 절대 작성하지 않는다. "
        f"{brand}이 상대의 속마음이나 미련을 알아낸다·볼 수 있다·맞혀 준다처럼 주어진 사실에 없는 "
        "능력도 지어내지 않는다 — 쓸 수 있는 것은 주어진 평판과 내 바람(궁금하다·보고 싶다·"
        "알아보고 싶다)이다.\n"
        f"{brand}을 말하는 문장도 사람이 평소 쓰는 자연스러운 한국어로 쓴다. 주어와 서술어가 "
        "맞아야 하고(사주를 보는 것은 "
        f"{brand}이다 — '{brand} 연애 사주가 잘 본다던데'처럼 쓰지 않는다), 들은 말을 문장 끝에 "
        "따로 덧붙이지 않는다('보고 싶네요, 잘 본다던데요'처럼 쓰지 않는다).\n"
        f"8. 글자 수는 설정된 {min_body}~{max_body}자다(넘으면 버려진다). 처음부터 그 안에 "
        f"들도록 공백 포함 {lo}~{hi}자쯤을 권장한다. 글자 수는 body의 본문만 센다 — "
        "concern·used_quote 같은 다른 칸은 세지 않는다. 광고 "
        f"표기({disclosure})는 프로그램이 별도로 붙이므로 본문에는 작성하지 않는다(글자 수에도 "
        "넣지 않는다).\n"
        "9. 대개 두세 문장이면 맞는다. 반응과 생각을 한 문장에 담아도 된다(문장 수는 "
        "자유다). 영상의 구체적인 장면과 생각의 연결은 지우지 않는다. 꾸미는 말, 되풀이, 영상 "
        "내용을 길게 옮기는 것을 줄여 처음부터 간결하게 쓴다 — 길게 쓴 뒤 줄이지 않는다.\n"
        f"{brand}에 대한 사실:\n{fact_lines}\n"
        "\n"
        "## 가장 중요한 원칙\n"
        f"- {brand}을 언급하기 직전의 생각이 왜 이 영상 내용에서 나왔는지 설명할 수 없다면, 그 "
        "댓글은 처음부터 다시 쓴다.\n"
        f"- {brand} 직전의 생각이 다른 연애 영상 댓글에 그대로 붙여도 말이 되는 막연한 것(연애 "
        "흐름이 궁금해요, 제 연애운이 궁금해요)이면 안 된다 — 이 영상의 고민에서 나온 생각이어야 "
        "한다.\n"
        f"- 영상 이야기와 {brand} 이야기가 하나의 맥락으로 이어져야 한다.\n"
        "- 글의 처음과 끝이 같은 사람이 쓴 것처럼 느껴져야 한다.\n"
        "- 앞에서 등장하지 않은 인물이나 관계를 끝에서 갑자기 언급하지 않는다.\n"
        "- 억지 연결 문장은 작성하지 않는다.\n"
        "- 브랜드를 언급하기 위해 영상의 핵심 고민을 다른 주제로 바꾸지 않는다.\n"
        "- 이전 댓글과 표현이 일부 비슷해도 괜찮다. 영상에 대한 내용과 전체 댓글이 사실상 동일한 "
        "경우만 피한다.\n"
        "\n"
        "## 피해야 할 흐름\n"
        "영상: 애인이 시간을 갖자고 할 때 어떻게 답해야 하는가\n"
        f"나쁜 글: 다시 얘기할 날짜를 정하라는 말이 좋네요. 저도 연애 흐름이 궁금해요. 요즘 "
        f"{brand} 연애 사주 잘 본다던데 보고 싶어요.\n"
        "- 날짜를 정하자는 얘기에서 연애 흐름으로 갑자기 바뀐다\n"
        f"- {brand}이 나오는 이유가 없다\n"
        "- 앞부분을 다른 연애 영상으로 바꿔도 뒷부분을 그대로 쓸 수 있다\n"
        "\n"
        "## 참고 예시\n"
        f"{best}\n"
        "이 예시는 자연스럽게 생각이 이어지는 방식만 참고한다. 문장, 말투, 연결 표현을 그대로 "
        "복사하지 않는다.\n"
        f"{longer}"
        "\n"
        "## 작성 후 검토\n"
        "댓글 전체를 한 번 읽고 다음을 판단한다.\n"
        "- 영상에서 다루는 고민이 댓글 끝까지 이어지는가?\n"
        f"- {brand}을 꺼내기 직전의 생각이 이 영상의 어떤 내용에서 나왔는지 설명할 수 있는가?\n"
        "- 사주를 꺼내려고 지어낸 궁금증이나, 사주로 볼 일이 아닌 것을 사주에서 알아보겠다는 "
        "말은 없는가?\n"
        "- 글쓴이의 관점이 처음부터 끝까지 일관적인가?\n"
        f"- {brand}이 뜬금없이 등장하지 않는가?\n"
        f"- {brand}을 직접 이용한 것처럼 쓴 허위 후기가 없는가?\n"
        "어색하다면 문장을 덧붙여 억지로 연결하지 말고, 댓글 전체를 처음부터 다시 작성한다.\n"
        "\n"
        "## 출력\n"
        "다음 JSON 형식으로만 답한다.\n"
        "{\"concern\": \"영상의 핵심 연애 고민 한 줄\", "
        f"\"body\": \"완성된 댓글 본문(권장 공백 포함 {lo}~{hi}자)\", "
        "\"used_quote\": \"댓글 작성에 사용한 영상 자료의 실제 근거 구절\", \"tone_label\": "
        "\"댓글에 실제 사용한 말투 유형(" + "·".join(TONE_LABELS) + " 가운데 하나)\"}\n"
        "중간 문장 조각은 따로 만들지 않는다. 최종 댓글은 처음부터 끝까지 하나의 글로 작성한다."
    )


def story_schema() -> dict[str, Any]:
    """이야기 방식 초안 스키마 — 고민(concern)만 본문보다 먼저 정리한다(조각 칸은 없다)."""
    schema = prompts.draft_schema(TONE_LABELS)
    return {
        **schema,
        "properties": {"concern": {"type": "string"}, **schema["properties"]},
        "required": ["concern", *schema["required"]],
    }


def drop_quotes(body: str) -> str:
    """따옴표를 지운다(2026-11-18 대표: 시청자는 영상 속 말을 따옴표로 옮겨 적지 않는다)."""
    text = body.translate({ord(c): None for c in QUOTE_MARKS})
    return " ".join(text.split())


MATERIAL_TRANSCRIPT = 2500  # 요청 글에 넣는 자막 글자 수(앞부분)
MATERIAL_COMMENTS = 10  # 요청 글에 넣는 인기 댓글 수


def material(*, title: str, description: str, transcript: str,
             comments: Sequence[str]) -> str:
    """AI가 직접 읽을 영상 자료: 제목 · 자막(없으면 없다고) · 설명 · 인기 댓글."""
    lines = [f"제목: {title or '(모름)'}"]
    if transcript.strip():
        lines.append(f"자막: {' '.join(transcript.split())[:MATERIAL_TRANSCRIPT]}")
    else:
        lines.append("자막: 없음(제목·설명과 인기 댓글을 보고 쓴다)")
    if description.strip():
        lines.append(f"설명: {' '.join(description.split())[:400]}")
    top = [" ".join(t.split())[:200] for t in comments if t and t.strip()][:MATERIAL_COMMENTS]
    if top:
        lines.append("인기 댓글:")
        lines += [f"  · {t}" for t in top]
    return "\n".join(lines)


def story_user(
    *,
    analysis: Mapping[str, Any],
    title: str,
    quote: str,
    source: str,
    key_phrases: Sequence[str] = (),
    mark_len: int = 0,
    max_body: int = 120,
    min_body: int = 40,
    brand: str = "운명원",
    shown: Sequence[str] = (),
    avoid_bodies: Sequence[str] = (),
    failure_lines: Sequence[str] = (),
    previous_body: str = "",
    drop: int = 0,
    thin: bool = False,
    material_text: str = "",
) -> str:
    """이야기 방식의 요청 글: 영상 자료 · 영상 요약 · 실제 영상 근거 구절 · 작성 조건(+ 다시 쓰기).

    `material_text`: `material()`로 만든 자료(없으면 분석 요약만 보인다).
    `key_phrases`·`mark_len`·`thin`은 예전 인자(요청 글에 쓰지 않는다).
    `drop`: 길이로 세 번 다 걸린 뒤 더 짧게 쓰라는 차례.
    """
    del key_phrases, mark_len, thin
    parts = ["[영상 자료]", material_text or f"제목: {title or '(모름)'}"]
    # 2026-11-18 대표 5단계: 분석이 만든 요약(주제·핵심 연애 고민)과 실제 근거 구절을 함께 넘긴다
    if analysis.get("topic") or analysis.get("concern"):
        parts += [
            "",
            "[영상 요약]",
            f"주제: {analysis.get('topic', '')}",
            f"핵심 연애 고민: {analysis.get('concern', '')}",
        ]
    parts += [
        "",
        "[실제 영상 근거 구절]",
        f"{quote} ({SOURCE_LABELS.get(source, source)})",
        "",
        "[작성 조건]",
        # 2026-11-18 대표: 상한을 목표로 주면 넘친다 — 목표는 상한보다 낮게, 상한은 따로 알린다
        "본문 글자 수: {}~{}자(넘으면 버려진다). 권장: 공백 포함 {}~{}자쯤.".format(
            min_body, max_body, *story_target(min_body=min_body, max_body=max_body)),
        "광고 표기는 프로그램에서 별도로 추가한다.",
        "",
        "영상에서 실제로 확인되는 내용을 하나 이상 언급하고,",
        f"영상의 연애 고민에서 {brand}에 가 보고 싶은 마음까지",
        "자연스럽게 이어지는 댓글 하나를 작성한다.",
    ]
    if drop and drop < len(DROP_LINES):
        parts.append(DROP_LINES[drop])
    recent = list(dict.fromkeys(t for t in shown if t))[:MAX_SHOWN]
    if recent:
        parts += ["", "[이미 쓴 댓글 — 전체가 사실상 같은 글만 피한다]"]
        parts += [f"- {t}" for t in recent]
    if avoid_bodies:
        parts += ["", "[같은 영상에 이미 쓴 초안 — 사실상 같은 글만 피한다]"]
        parts += [f"- {b}" for b in list(avoid_bodies)[:3]]
    if failure_lines:
        parts += [
            "",
            "[다시 쓰기] 앞의 본문이 검사에 걸렸다.",
            f"앞의 본문({len(previous_body)}자): {previous_body}",
            "걸린 항목:",
            *[f"- {line}" for line in failure_lines],
            "걸린 항목을 고쳐 댓글 전체를 다시 쓴다(문장을 덧붙여 억지로 잇지 않는다).",
        ]
        if any("깁니다" in line for line in failure_lines):
            parts.append(SHORTEN_LINE.format(brand=brand))
    return "\n".join(parts)
