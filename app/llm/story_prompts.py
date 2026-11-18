"""이야기처럼 쓰기 프롬프트(2026-11-18 대표 결정, `comment.writer: story`).

대표가 정한 것만 지시한다: 설정 글자 수(표기 빼고 40~120자) · 자막(없으면 제목·설명)과 인기 댓글을
읽고 영상의 연애 고민을 먼저 정리한 뒤 시청자 입장에서 기승전결로 · 운명원 사주를 보고 싶어지게.
단서는 영상 속 구체적인 장면·말 하나 이상, 써 본 척하는 후기 금지, 장면과 운명원의 맥락 이어짐.
본보기는 과제 예시 하나. 코드는 대표 표의 규칙 검사·S4, AI는 맥락 일치 검증을 본다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.analysis.validator import ASSIGNMENT_SAMPLE
from app.llm import prompts
from app.llm.prompts import SOURCE_LABELS, TONE_LABELS, _quoted

# 대표가 직접 고친 글(2026-11-18) — 과제 예시 다음으로 보여 준다
BOSS_EXAMPLE = (
    "'언제 한번 보자' 말고 날짜부터 잡는다니 괜히 설레네요ㅋㅋ 저도 호감 신호를 잘 헷갈리는 "
    "편이라.. 그 사람도 저한테 반한 건지 궁금해요. 요새 운명원이 연애 사주 잘 본다던데 그 "
    "사람이랑 궁합 보러 가고 싶어요"
)
STORY_TARGET = (75, 95)  # 대표: 표기 빼고 120자. 루나가 알린 목표보다 15~25자 길게 써서 낮게 알린다
MAX_SHOWN = 6  # 「이미 쓴 글」로 보여 줄 앞 초안 수

# 길이로 세 번 다 걸렸을 때 덜어 낼 것(차례대로)
DROP_LINES = (
    "",
    "이번에는 **이음 문장을 쓰지 않는다** — 반응 · 내 처지 다음에 바로 운명원 문장으로 간다.",
    "이번에는 **세 문장만** 쓴다 — 반응 한 문장 · 내 처지 한마디 · 운명원 문장.",
)


def story_system(*, brand: str, disclosure: str, facts: Sequence[str], sample: str = "") -> str:
    """이야기 방식의 시스템 글(2026-11-18 대표: 불필요한 제한은 빼고 아래만).

    1. 설정 글자 수(40~120자, 표기 빼고) 2. 자막(없으면 제목·설명)과 인기 댓글을 읽고 영상이 다루는
    연애 고민을 먼저 정리한 뒤, 영상을 본 시청자 입장에서 기승전결로 쓴다 3. 운명원 사주를 보고
    싶어지게. 단서 — 영상 속 구체적인 장면·말을 하나 이상, 운명원을 써 본 척하는 후기 금지, 앞의
    장면과 운명원의 맥락이 이어지게. 과제 예시가 가장 좋은 본보기다.
    """
    fact_lines = "\n".join(f"- {f}" for f in facts) or (
        f"- {brand}은 연애 사주를 잘 봐주는 곳으로 유명하다"
    )
    best = sample or ASSIGNMENT_SAMPLE
    return (
        "너는 방금 유튜브 연애 영상을 본 시청자 한 사람이다. 그 영상에 댓글 하나를 단다.\n"
        "\n"
        "1. 아래 [영상 자료](자막, 자막이 없으면 제목·설명, 그리고 인기 댓글)를 읽고 이 영상이 "
        "다루는 연애 고민을 먼저 한 줄로 정리한다(concern 칸).\n"
        "2. 그 영상을 본 시청자 입장에서 기승전결로 댓글을 쓴다 — 영상 속 구체적인 장면이나 말을 "
        "하나 이상 짚어 반응하고(기), 내 처지로 받아들이고(승), 생각이 이어져(전), "
        f"{brand}으로 맺는다(결). 처음부터 끝까지 한 사람의 목소리로, 앞의 장면과 {brand} 얘기가 "
        "맥락이 이어지게 쓴다.\n"
        f"3. 읽는 사람이 {brand}에서 연애 사주를 보고 싶어지게 끝낸다 — '{brand}이 연애 사주 잘 "
        "본다던데'처럼 들은 얘기로 꺼내고('요새', '요즘', '친구한테 듣기로' 같은 추임새를 앞서 쓴 "
        "글과 겹치지 않게 붙인다), 앞 이야기에서 나온 **무엇을 보고 싶은지**(그 사람 마음, 둘의 "
        "궁합, 언제 인연이 오는지 …)를 넣어 보러 가고 싶다는 마음으로 맺는다.\n"
        "\n"
        "단,\n"
        "- 영상 자료에 실제로 있는 내용만 쓴다. 자막이 없으면 제목·설명·인기 댓글처럼 확인할 수 "
        "있는 것만 쓰고, 없는 장면이나 발언을 만들어 내지 않는다. 다른 시청자의 댓글이면 '~라는 "
        "댓글 "
        "보고'처럼 댓글이라고 밝힌다.\n"
        f"- {brand}을 꺼내려고 영상과 상관없는 이야기를 억지로 붙이지 않는다.\n"
        f"- {brand}을 직접 이용해 본 것처럼 지어낸 후기는 쓰지 않는다('받아 봤어요', '다녀왔어요', "
        "'맞더라고요' ✗). 보러 가고 싶다는 마음까지만.\n"
        f"- {brand}에 대해서는 아래 사실과 '잘 본다던데' 같은 들은 얘기까지만 쓴다.\n"
        f"- 홍보 표기 {disclosure}는 쓰지 않는다(프로그램이 앞에 붙인다). body에는 본문만.\n"
        f"{brand}에 대한 사실:\n{fact_lines}\n"
        "\n"
        "가장 좋은 본보기(다른 영상 이야기다 — 흐름만 배우고 문장은 베끼지 않는다):\n"
        f"{best}\n"
        "대표가 직접 고친 글(영상 속 말을 내 말로 받고, 내 처지 → 궁금한 것 → 운명원이 한 줄로 "
        f"이어진다):\n{BOSS_EXAMPLE}\n"
        "\n"
        "출력은 JSON 객체 하나: {\"concern\": 이 영상이 다루는 연애 고민 한 줄, \"body\": 댓글 "
        "본문, \"used_quote\": 본문에서 짚은 영상 속 말, \"tone_label\": "
        + "·".join(TONE_LABELS) + " 가운데 댓글 분위기에 맞는 것}"
    )


def story_schema() -> dict[str, Any]:
    """이야기 방식 초안 스키마 — 영상의 연애 고민(concern)을 본문보다 먼저 정리하게 한다."""
    schema = prompts.draft_schema(TONE_LABELS)
    return {
        **schema,
        "properties": {"concern": {"type": "string"}, **schema["properties"]},
        "required": ["concern", *schema["required"]],
    }


MATERIAL_TRANSCRIPT = 2500  # 요청 글에 넣는 자막 글자 수(앞부분)
MATERIAL_COMMENTS = 10  # 요청 글에 넣는 인기 댓글 수


def material(*, title: str, description: str, transcript: str,
             comments: Sequence[str]) -> str:
    """AI가 직접 읽을 영상 자료(대표: 자막 — 없으면 제목·설명 — 과 인기 댓글)."""
    lines = [f"- 제목: {title or '(모름)'}"]
    if description.strip():
        lines.append(f"- 설명: {' '.join(description.split())[:400]}")
    if transcript.strip():
        lines.append(f"- 자막: {' '.join(transcript.split())[:MATERIAL_TRANSCRIPT]}")
    else:
        lines.append("- 자막: 없음(제목·설명과 인기 댓글을 보고 쓴다)")
    top = [" ".join(t.split())[:200] for t in comments if t and t.strip()][:MATERIAL_COMMENTS]
    if top:
        lines.append("- 인기 댓글:")
        lines += [f"  · {t}" for t in top]
    return "\n".join(lines)


def story_target(*, mark_len: int, max_body: int) -> tuple[int, int]:
    """본문(표기 뺀 것)의 목표 글자 수. 표기는 세지 않으므로 `mark_len`은 보통 0이다."""
    lo = max(1, STORY_TARGET[0] - mark_len)
    hi = min(max_body, STORY_TARGET[1] - mark_len)
    return lo, max(lo, hi)


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
    """이야기 방식의 요청 글: 영상 자료 원문 + 짚을 만한 말 + 글자 수 + 이미 쓴 글 + (다시 쓰기).

    `material_text`: `material()`로 만든 자막·제목·설명·인기 댓글(없으면 분석 요약만 보인다).
    `mark_len`: 예전 셈(표기 몫)을 시험하려고 남겨 둔 값 — 앱은 0을 넘긴다(표기는 세지 않는다).
    `drop`: 길이로 세 번 다 걸렸을 때 덜어 낼 차례(1: 이음 문장, 2: 세 문장만).
    """
    del brand  # 예전 인자(요청 글에는 쓰지 않는다)
    lo, hi = story_target(mark_len=mark_len, max_body=max_body)
    phrases = [p for p in key_phrases if p]
    parts = ["[영상 자료]", material_text or (
        f"- 제목: {title or '(모름)'}\n- 주제: {analysis.get('topic', '')}\n"
        f"- 시청자 고민 한 줄: {analysis.get('concern', '')}"
    )]
    if thin:
        parts.append("이 영상은 자막이 없다 — 제목·설명이나 인기 댓글 속 말에 반응한다. 댓글이면 "
                     "'~라는 댓글 보고'처럼 댓글이라고 밝힌다. 짧게 써도 된다.")
    hint = f"[짚을 만한 말] '{quote}' ({SOURCE_LABELS.get(source, source)})"
    if phrases:
        hint += (f" · 핵심 말 {_quoted(phrases)} — 이 중 하나나 영상 자료 속 다른 구체적인 말을 "
                 "하나 이상 넣는다(풀이말은 끝을 바꿔도 된다)")
    parts.append(hint)
    parts.append(
        f"[글자 수] 본문 {min_body}~{max_body}자(표기는 세지 않는다"
        + (f", 표기 몫 {mark_len}자 뺐음" if mark_len else "")
        + f"). {lo}~{hi}자쯤이 알맞다. 쓰고 나서 세어 보고 넘으면 문장 하나를 통째로 뺀다."
    )
    if drop and drop < len(DROP_LINES):
        parts.append(DROP_LINES[drop])
    recent = list(dict.fromkeys(t for t in shown if t))[:MAX_SHOWN]
    if recent:
        parts.append("[이미 쓴 글 — 똑같이 쓰지 않는다]")
        parts += [f"- {t}" for t in recent]
    if avoid_bodies:
        parts.append("[같은 영상에 이미 쓴 초안 — 다른 장면·흐름으로]")
        parts += [f"- {b}" for b in list(avoid_bodies)[:3]]
    if failure_lines:
        parts += [
            "",
            "[다시 쓰기] 앞의 본문이 검사에 걸렸다.",
            f"앞의 본문({len(previous_body)}자): {previous_body}",
            "걸린 항목(고치는 법):",
            *[f"- {line}" for line in failure_lines],
            "걸린 항목을 고쳐 새 본문을 써라.",
        ]
    return "\n".join(parts)
