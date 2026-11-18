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

2026-11-18 대표(기준 예시 확정): 영상을 해설·분석하는 사람이 아니라 영상을 보고 자기 고민이 떠오른
사람의 대화체(설명문·광고 카피가 아님), 운명원을 떠올린 까닭은 설명 문장을 더하지 않아도 앞
이야기에서 느껴지게. 참고 예시를 대표의 기준 예시(`BOSS_SAMPLE`) 하나로 바꾸고 「문장·끝말을 그대로
옮기지 않는다, 화자의 목소리와 흐름만」을 붙였다. 끝을 「인연」으로 몰던 「인연·궁합·연애운·때
쪽이면 그 얘기로」와 길 예의 「인연이라는 게 있나 싶다」를 덜어 냈다.

2026-11-18 대표(기준 예시판 22개를 읽고 「단순화해라」): 22개 모두 「인연」, 거의 같은 운명원
문장과 결말 — 예시를 참고한 게 아니라 공식을 복제했다. 지시를 더하지 않고 걷어 냈다. 남긴 것은
누구로 쓰는가(이 영상을 방금 본 시청자가 평소 말하듯) · 꼭 들어갈 것(영상 속 장면 하나, 운명원과
연애 사주 — 영상을 보고 든 생각과 이어지게) · 하면 안 되는 것(영상에 없는 사실, 다른 고민으로
바꾸기, 실제로 겪은 것처럼 보이는 구체적인 사건, 이용 후기·효능·지어낸 평판·능력, 링크) · 글자 수 ·
출력뿐이다. 「반응 → 고민 → 사주 까닭 → 운명원」 짜임을 정하던 문구(목표 줄, 작성 방법 1·3·5·6·7·9,
가장 중요한 원칙, 피해야 할 흐름, 작성 후 검토)와 참고 예시(`BOSS_SAMPLE`)를 뺐다. 대표 기준 예시는
검수 회귀 사례로만 남는다. 지어낸 궁금증·사주로 볼 일이 아닌 것은 쓰는 쪽에서 빼고 검수가 본다
(「사주로 볼 일이 아닌 것」 금지가 「안전한 답은 인연」으로 몰았다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.llm import prompts
from app.llm.prompts import SOURCE_LABELS, TONE_LABELS

MAX_SHOWN = 6  # 「이미 쓴 글」로 보여 줄 앞 초안 수

QUOTE_MARKS = "'\"‘’“”「」『』"

# 길이로 걸려 다시 쓸 때만 덧붙이는 말(2026-11-18 대표: 120자는 과제 조건. 줄이면서 생각이 이어지는
# 부분이 먼저 잘렸다 — 처음 쓸 때는 아무것도 정하지 않고, 줄일 때 남길 것만 알린다)
SHORTEN_LINE = (
    "영상 속 장면과 {brand} 연애 사주 얘기는 지우지 말고 꾸미는 말·되풀이·영상 내용을 길게 옮긴 "
    "곳을 덜어 줄인다."
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
    *, brand: str, disclosure: str, facts: Sequence[str], min_body: int = 40, max_body: int = 120,
) -> str:
    """이야기 방식의 시스템 글(2026-11-18 대표 「단순화해라」): 누구로 쓰는가 · 꼭 들어갈 것 · 하면
    안 되는 것 · 글자 수 · 출력만 둔다. 글을 어떻게 짜는가(반응 → 고민 → 사주 까닭 → 운명원)와
    참고 예시는 넣지 않는다. 목표 길이는 `story_target`(본문 기준, 표기 켬/끔과 상관없다)."""
    lo, hi = story_target(min_body=min_body, max_body=max_body)
    fact_lines = "\n".join(f"- {f}" for f in facts) or (
        f"- {brand}은 연애 사주를 잘 봐주는 곳으로 유명하다"
    )
    return (
        "너는 유튜브 연애 영상에 달 한국어 댓글 하나를 쓴다. 영상 자료(제목·자막·설명·인기 댓글)를 "
        "읽고, 이 영상을 방금 본 시청자가 평소 말하듯 쓴다. 영상을 해설하거나 정리하는 글, 광고 "
        "카피처럼 쓰지 않는다.\n"
        "\n"
        "## 꼭 들어갈 것\n"
        "- 영상에 실제로 나온 구체적인 장면이나 말 하나. 따옴표로 옮기지 않고 내 말로 쓴다. 자막이 "
        "없으면 제목·설명에서 확인되는 내용을 쓴다.\n"
        f"- {brand}과 연애 사주 얘기. 영상을 보고 든 생각과 이어지게 쓴다 — 다른 영상에 그대로 "
        "붙여도 되는 말로 꺼내지 않는다.\n"
        "\n"
        "## 하면 안 되는 것\n"
        "- 영상에 없는 사실을 영상 얘기처럼 쓰기. 인기 댓글의 사연을 영상에서 나온 말처럼 쓰기.\n"
        "- 영상이 다루는 이야기를 다른 고민으로 바꾸기.\n"
        "- 실제로 겪은 것처럼 보이는 구체적인 사건 지어내기(내 애인·전 애인이 한 일, 내가 겪은 "
        "일).\n"
        f"- {brand}을 직접 이용하거나 상담받은 것처럼 쓴 후기, 효과를 단정하는 말, 아래 사실에 "
        "없는 평판·능력(상대의 속마음을 알아낸다 같은 것).\n"
        "- 링크·해시태그.\n"
        f"{brand}에 대한 사실:\n{fact_lines}\n"
        f"{brand}을 말하는 문장도 주어와 서술어가 맞는 자연스러운 한국어로 쓴다.\n"
        "\n"
        "## 길이\n"
        f"본문은 {min_body}~{max_body}자다(넘으면 버려진다). 처음부터 공백 포함 {lo}~{hi}자쯤으로 "
        f"간결하게 쓴다. 광고 표기({disclosure})는 프로그램이 붙이므로 본문에 쓰지 않는다.\n"
        "\n"
        "## 출력\n"
        "다음 JSON 하나로만 답한다.\n"
        "{\"concern\": \"영상이 다루는 내용 한 줄\", \"body\": \"댓글 본문\", "
        "\"used_quote\": \"댓글에 쓴 영상 자료의 실제 구절\", \"tone_label\": "
        "\"댓글의 말투 유형(" + "·".join(TONE_LABELS) + " 가운데 하나)\"}"
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
        "이 영상에 달 댓글 하나를 쓴다.",
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
