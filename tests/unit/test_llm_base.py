"""LLM 공통 코드: JSON 꺼내기, 스키마 확인(필수 키·자료형), 한 번 다시 시키기."""

import pytest

from app.errors import AppError
from app.llm.base import (
    BadOutput,
    LLMClient,
    LLMHealth,
    TextJSONLLM,
    check_schema,
    extract_json,
    parse_reply,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "concern": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"quote": {"type": "string"}, "source": {"type": "string"}},
                "required": ["quote", "source"],
            },
        },
    },
    "required": ["concern", "evidence"],
}
GOOD = {
    "concern": "연락이 줄어 불안하다",
    "evidence": [{"quote": "요즘 답장이 늦어요", "source": "자막"}],
}


# ---------------------------------------------------------------- extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_text_before_and_after_json():
    text = '네, 정리했습니다.\n{"concern": "이별 뒤 미련", "evidence": []}\n도움이 되셨길 바랍니다.'
    assert extract_json(text) == {"concern": "이별 뒤 미련", "evidence": []}


def test_json_in_code_block():
    text = '아래와 같습니다.\n```json\n{"concern": "짝사랑", "evidence": []}\n```\n끝.'
    assert extract_json(text) == {"concern": "짝사랑", "evidence": []}


def test_code_block_without_language():
    assert extract_json('```\n{"x": "가"}\n```') == {"x": "가"}


def test_braces_in_prose_before_real_json():
    # 앞 설명의 중괄호가 JSON이 아니어도 다음 후보를 본다
    text = '형식은 {이렇게} 입니다: {"ok": true}'
    assert extract_json(text) == {"ok": True}


def test_korean_and_nested_values():
    assert extract_json('{"a": {"b": ["가", "나"]}}') == {"a": {"b": ["가", "나"]}}


@pytest.mark.parametrize("text", ["", "   ", "JSON이 없는 답", '{"a": 1', "```json\n{깨짐}\n```"])
def test_no_json_raises(text):
    with pytest.raises(BadOutput):
        extract_json(text)


# ---------------------------------------------------------------- check_schema


def test_schema_ok():
    assert check_schema(GOOD, SCHEMA) == []


def test_missing_required_key():
    problems = check_schema({"concern": "x"}, SCHEMA)
    assert problems == ["$.evidence: 필수 키가 없습니다"]


def test_missing_key_inside_array_item():
    problems = check_schema({"concern": "x", "evidence": [{"quote": "q"}]}, SCHEMA)
    assert problems == ["$.evidence[0].source: 필수 키가 없습니다"]


def test_wrong_types():
    problems = check_schema({"concern": 3, "evidence": "목록 아님"}, SCHEMA)
    assert "$.concern: string 자료형이어야 합니다" in problems
    assert "$.evidence: array 자료형이어야 합니다" in problems


def test_bool_is_not_number_and_int_is_number():
    assert check_schema(True, {"type": "integer"})
    assert check_schema(3, {"type": "number"}) == []
    assert check_schema(3.5, {"type": "integer"})


def test_type_list_and_enum():
    assert check_schema(None, {"type": ["string", "null"]}) == []
    assert check_schema("공감형", {"type": "string", "enum": ["공감형", "조언형"]}) == []
    assert check_schema("기타", {"type": "string", "enum": ["공감형", "조언형"]})


def test_extra_keys_are_allowed():
    assert check_schema({**GOOD, "note": "더 있음"}, SCHEMA) == []


def test_parse_reply_requires_object():
    with pytest.raises(BadOutput, match="객체"):
        parse_reply("[1, 2]", SCHEMA)
    with pytest.raises(BadOutput, match="필수 키"):
        parse_reply('{"concern": "x"}', SCHEMA)
    assert parse_reply(f"답: {__import__('json').dumps(GOOD, ensure_ascii=False)}", SCHEMA) == GOOD


# ---------------------------------------------------------------- 한 번 다시 시키기


class ScriptedLLM(TextJSONLLM):
    provider = "test"
    model = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def _complete(self, *, system, user, schema, temperature, max_tokens):
        self.prompts.append(user)
        return self.replies.pop(0)

    def health(self):
        return LLMHealth(self.provider, self.model, True, True, True)

    def warmup(self):
        return 0.0

    def close(self):
        pass


def test_first_reply_ok_no_retry():
    llm = ScriptedLLM(['{"concern": "a", "evidence": []}'])
    assert llm.generate_json(system="s", user="u", schema=SCHEMA) == {
        "concern": "a",
        "evidence": [],
    }
    assert llm.prompts == ["u"]


def test_broken_then_ok_retries_once_with_reason():
    llm = ScriptedLLM(["죄송해요, 잘 모르겠어요", '{"concern": "a", "evidence": []}'])
    assert llm.generate_json(system="s", user="u", schema=SCHEMA)["concern"] == "a"
    assert len(llm.prompts) == 2
    assert llm.prompts[1].startswith("u")
    assert "다시 요청" in llm.prompts[1] and "JSON을 찾지 못했습니다" in llm.prompts[1]


def test_schema_mismatch_then_ok():
    llm = ScriptedLLM(['{"concern": "a"}', '{"concern": "a", "evidence": []}'])
    assert llm.generate_json(system="s", user="u", schema=SCHEMA)["evidence"] == []
    assert "$.evidence: 필수 키가 없습니다" in llm.prompts[1]


def test_both_broken_raises_bad_output():
    llm = ScriptedLLM(["깨짐", '{"concern": 1}'])
    with pytest.raises(AppError) as info:
        llm.generate_json(system="s", user="u", schema=SCHEMA)
    assert info.value.kind == "llm_bad_output"
    assert "test · scripted" in info.value.detail
    assert len(llm.prompts) == 2


def test_scripted_llm_follows_protocol():
    assert isinstance(ScriptedLLM([]), LLMClient)


def test_health_to_dict_shape():
    health = LLMHealth("ollama", "qwen2.5:7b", True, False, True)
    assert health.to_dict() == {
        "provider": "ollama",
        "model": "qwen2.5:7b",
        "reachable": True,
        "installed": False,
        "local": True,
    }
    assert health.ok is False
