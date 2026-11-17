"""LLM 공통 규격과 공통 코드(DESIGN 5.2.1).

분석·초안 코드(5단계)는 이 파일의 `LLMClient` 규격만 안다. 어느 회사·어느 서버의
모델인지는 `app/llm/registry.py`가 설정(`llm.active`)을 보고 정한다.

- `generate_json(*, system, user, schema, temperature, max_tokens) -> dict`
- `health() -> LLMHealth(provider, model, reachable, installed, local)`
- `warmup() -> float` 모델을 미리 불러 두고 걸린 초를 돌려준다

공통 코드: 받은 글에서 JSON 꺼내기(`extract_json`), 스키마와 맞는지 확인(`check_schema`,
필수 키와 자료형만 보는 작은 검사), 안 맞으면 한 번 다시 시키기(`TextJSONLLM`).
스키마 강제를 지원하는 공급자(Ollama `format`)도 같은 확인을 거친다 — 모델이 스키마를
어겨도 화면까지 깨진 값이 가지 않게 한다.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Protocol, runtime_checkable

from app.errors import AppError, ErrorKind

JSONSchema = dict[str, Any]


@dataclass(frozen=True)
class LLMHealth:
    """위 줄 AI 상태. `local`이 거짓이면 화면에 「외부」로 보인다."""

    provider: str  # 설정의 공급자 이름(llm.active)
    model: str
    reachable: bool  # 서버(또는 API)에 닿는가
    installed: bool  # 그 모델을 쓸 수 있는가
    local: bool  # 이 PC 안에서 도는가(영상 자료가 밖으로 나가지 않는가)

    @property
    def ok(self) -> bool:
        return self.reachable and self.installed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class LLMClient(Protocol):
    provider: str
    model: str
    local: bool

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema: JSONSchema,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> dict[str, Any]: ...

    def health(self) -> LLMHealth: ...

    def warmup(self) -> float: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------- JSON 꺼내기


class BadOutput(ValueError):
    """모델의 답에서 스키마에 맞는 JSON을 얻지 못했다(재시도 사유가 메시지)."""


_FENCE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)```", re.S)


def extract_json(text: str) -> Any:
    """모델이 돌려준 글에서 JSON 값 하나를 꺼낸다.

    순서: 글 전체 → ```json 코드 블록``` 안 → 처음 나오는 `{`·`[`부터 읽을 수 있는 만큼.
    앞뒤에 설명이 붙어 있어도 꺼낸다. 하나도 못 읽으면 `BadOutput`.
    """
    if not isinstance(text, str) or not text.strip():
        raise BadOutput("답이 비어 있습니다.")
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    for block in _FENCE.findall(stripped):
        try:
            return json.loads(block.strip())
        except ValueError:
            continue
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[{\[]", stripped):
        try:
            value, _ = decoder.raw_decode(stripped, match.start())
        except ValueError:
            continue
        return value
    raise BadOutput("답에서 JSON을 찾지 못했습니다.")


# ---------------------------------------------------------------- 스키마 확인

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def _type_ok(value: Any, expected: str) -> bool:
    if expected not in _TYPES:
        return True  # 모르는 자료형 이름은 검사하지 않는다(작은 검사기)
    if isinstance(value, bool) and expected in ("integer", "number"):
        return False  # JSON의 true는 숫자가 아니다
    return isinstance(value, _TYPES[expected])


def check_schema(value: Any, schema: JSONSchema, path: str = "$") -> list[str]:
    """필수 키와 자료형만 본다. 문제를 한 줄씩 돌려준다(빈 목록이면 맞음).

    다루는 것: `type`(문자열 또는 목록), `required`, `properties`, `items`, `enum`.
    길이·형식 같은 나머지 조건은 6단계 규칙 검사와 각 단계 코드가 맡는다.
    """
    problems: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        names = [expected] if isinstance(expected, str) else list(expected)
        if not any(_type_ok(value, name) for name in names):
            problems.append(f"{path}: {'·'.join(names)} 자료형이어야 합니다")
            return problems
    if "enum" in schema and value not in schema["enum"]:
        problems.append(
            f"{path}: 정해진 값({', '.join(map(str, schema['enum']))}) 중 하나여야 합니다"
        )
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path}.{key}: 필수 키가 없습니다")
        for key, sub in (schema.get("properties") or {}).items():
            if key in value and isinstance(sub, dict):
                problems.extend(check_schema(value[key], sub, f"{path}.{key}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            problems.extend(check_schema(item, schema["items"], f"{path}[{i}]"))
    return problems


def parse_reply(text: str, schema: JSONSchema) -> dict[str, Any]:
    """답 글 → 스키마에 맞는 dict. 안 맞으면 `BadOutput`(사유 포함)."""
    value = extract_json(text)
    if not isinstance(value, dict):
        raise BadOutput("답이 JSON 객체({ ... })가 아닙니다.")
    problems = check_schema(value, schema)
    if problems:
        raise BadOutput("; ".join(problems[:5]))
    return value


def schema_text(schema: JSONSchema) -> str:
    return json.dumps(schema, ensure_ascii=False)


def retry_note(reason: str, schema: JSONSchema) -> str:
    """두 번째 시도 때 사용자 메시지 끝에 붙이는 안내."""
    return (
        "\n\n[다시 요청] 앞의 답은 정해진 모양이 아니었습니다"
        f"({reason}). 다른 글 없이 아래 JSON 스키마에 맞는 JSON 객체 하나만 답하세요.\n"
        f"{schema_text(schema)}"
    )


# ---------------------------------------------------------------- 공통 구현


class TextJSONLLM(ABC):
    """`_complete`(글 한 번 받기)만 구현하면 JSON 꺼내기·확인·한 번 다시 시키기가 붙는다."""

    provider: str = ""
    model: str = ""
    local: bool = True
    max_attempts: int = 2  # 처음 + 다시 한 번
    # R5: JSON으로 답하지 않았을 때의 「다음에 할 일」(Ollama가 아닌 AI는 설정 화면을 가리킨다)
    bad_output_action: str | None = None

    @abstractmethod
    def _complete(
        self,
        *,
        system: str,
        user: str,
        schema: JSONSchema,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """모델에게 한 번 묻고 답 글을 돌려준다. 연결 오류는 `AppError`로 바꿔 던진다."""

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema: JSONSchema,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        prompt = user
        reasons: list[str] = []
        for _ in range(self.max_attempts):
            text = self._complete(
                system=system,
                user=prompt,
                schema=schema,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            try:
                return parse_reply(text, schema)
            except BadOutput as exc:
                reasons.append(str(exc))
                prompt = user + retry_note(str(exc), schema)
        raise AppError(
            ErrorKind.LLM_BAD_OUTPUT,
            detail=f"{self.provider} · {self.model}: " + " / ".join(reasons),
            action=self.bad_output_action,
        )
