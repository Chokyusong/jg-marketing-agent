"""프로그램 안에서 바꾼 설정(R2). 사용자가 파일을 열지 않고 모든 준비를 끝내게 한다.

- 위치: `%LOCALAPPDATA%\\JGMarketingAgent\\`(저장소 밖). 바꾼 값은 `settings.json`, 유튜브 API 키는
  `youtube_key.bin`(Windows DPAPI로 암호화. 파일에 평문이 없다). 테스트는 폴더를 임시 폴더로 바꾼다.
- 읽는 순서: **사용자 설정 → 환경 변수·`.env`(개발용, 없어도 된다) → `config.yaml`(기본값)**.
  `settings.json`에는 사용자가 바꾼 칸만 들어간다(`config.yaml`의 나머지는 그대로 쓴다).
- 칸 하나하나는 `FIELDS`에 이름·종류·범위를 적고, `validate()`가 잘못된 칸과 이유를
  한국어로 돌려준다.
  `apply_overlay()`는 `config.yaml` 내용(dict)에 바꾼 값을 덮어 `load_settings`가 그대로 읽게 한다.
- 키 값은 어떤 응답·화면·기록에도 돌려주지 않는다. 이 모듈도 키를 로그에 찍지 않는다.
- R5: 글 쓰는 AI의 API 키는 AI마다 따로 `llm_keys/<이름>.bin`(유튜브 키와 같은 DPAPI). 유튜브 키
  파일(`youtube_key.bin`)과 그 동작은 그대로다. AI 고르기(`llm.active`), AI별 모델(`llm.models`),
  「직접 입력」 주소(`llm.base_urls`)는 `settings.json`에.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("app.user_settings")

USER_DIR_ENV = "JG_USER_DIR"  # 사용자 설정 폴더를 바꿀 때(다른 PC·확인용). 비우면 아래 기본
SETTINGS_FILE = "settings.json"
KEY_FILE = "youtube_key.bin"
LLM_KEY_DIR = "llm_keys"  # R5: AI별 API 키(<이름>.bin, DPAPI)
FILE_VERSION = 1

# 글자 입력 속도(글자마다 기다리는 밀리초 최소·최대). 보통이 config.yaml의 기본값과 같다
TYPING_SPEEDS: dict[str, tuple[int, int]] = {
    "slow": (120, 260),
    "normal": (60, 160),
    "fast": (25, 70),
}
TYPING_SPEED_LABELS = {"slow": "느리게", "normal": "보통", "fast": "빠르게"}
# 2026-11-18 댓글 쓰는 방식(`app/analysis/story.py`의 WRITER_LABELS와 같은 말)
WRITER_LABELS = {"story": "이야기처럼(권장)", "pieces": "조각 맞추기(예전)"}
# 2026-11-18 대표: 게시 뒤 크롬 창. 열어 두기를 고르면 config.yaml의 초(0이면 300초)를 쓴다
AFTER_POST_WINDOW_LABELS = {"keep": "열어 두기(5분)", "close": "바로 닫기"}
KEEP_WINDOW_DEFAULT_SECONDS = 300
_KEY_SHAPE = re.compile(r"^[A-Za-z0-9_\-]{20,200}$")
# R5: AI 이름(파일 이름에 쓴다), 모델 이름(명령 인자로도 넘기므로 '-'로 시작하지 못하게), 주소
PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,39}$")
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-\[\]]{0,199}$")
_URL = re.compile(r"^https?://[^\s/?#]+(?::\d+)?(?:/[^\s?#]*)?$")
# AI 서비스 키는 회사마다 모양이 달라(sk-…, xai-…, AIza…) 넓게 본다: 빈칸 없는 글자 8~400자
_LLM_KEY_SHAPE = re.compile(r"^[!-~]{8,400}$")


def default_user_dir(environ: dict[str, str] | None = None) -> Path:
    """`%LOCALAPPDATA%/JGMarketingAgent`. `JG_USER_DIR`가 있으면 그 폴더."""
    env = os.environ if environ is None else environ
    override = (env.get(USER_DIR_ENV) or "").strip()
    if override:
        return Path(override)
    base = (env.get("LOCALAPPDATA") or "").strip() or str(Path.home() / "AppData" / "Local")
    return Path(base) / "JGMarketingAgent"


# ---------------------------------------------------------------- 비밀값 암호화(DPAPI)


class SecretStoreUnavailable(RuntimeError):
    """이 PC에서는 키를 암호화해 저장할 수 없다(Windows가 아님)."""


@dataclass(frozen=True)
class Protector:
    """암호화·복호화 함수 한 쌍. 테스트는 가짜로 바꿔 끼운다."""

    protect: Callable[[bytes], bytes]
    unprotect: Callable[[bytes], bytes]
    available: bool = True


def _dpapi(data: bytes, *, encrypt: bool) -> bytes:  # pragma: no cover - Windows 전용
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DataBlob()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN: 창을 띄우지 않는다
    if encrypt:
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in), "JGMarketingAgent", None, None, None, flags,
            ctypes.byref(blob_out),
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, flags, ctypes.byref(blob_out)
        )
    if not ok:
        raise OSError("DPAPI 호출 실패")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _unavailable(_data: bytes) -> bytes:
    raise SecretStoreUnavailable("이 PC에서는 키를 암호화해 저장할 수 없습니다")


def default_protector() -> Protector:
    """Windows면 DPAPI(지금 사용자 계정으로만 풀린다), 아니면 저장을 거절하는 것."""
    if sys.platform == "win32":
        return Protector(
            protect=lambda b: _dpapi(b, encrypt=True),
            unprotect=lambda b: _dpapi(b, encrypt=False),
        )
    return Protector(protect=_unavailable, unprotect=_unavailable, available=False)


# ---------------------------------------------------------------- 저장소


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class UserStore:
    """사용자 설정 폴더 하나. 값(`settings.json`)과 암호화한 키(`youtube_key.bin`)."""

    def __init__(self, root: Path, protector: Protector | None = None) -> None:
        self.root = Path(root)
        self.protector = protector or default_protector()

    @property
    def settings_path(self) -> Path:
        return self.root / SETTINGS_FILE

    @property
    def key_path(self) -> Path:
        return self.root / KEY_FILE

    # -- 값

    def read_values(self) -> dict[str, Any]:
        """저장한 값(칸 이름 → 값). 파일이 없거나 깨졌으면 빈 dict(기본값으로 돈다)."""
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.warning("사용자 설정 파일을 읽지 못해 기본값으로 씁니다")
            return {}
        values = raw.get("values") if isinstance(raw, dict) else None
        if not isinstance(values, dict):
            return {}
        return {k: v for k, v in values.items() if k in FIELDS}

    def write_values(self, values: dict[str, Any]) -> None:
        body = {"version": FILE_VERSION, "values": values}
        text = json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True)
        _atomic_write(self.settings_path, text.encode("utf-8"))

    def clear_values(self) -> None:
        self.settings_path.unlink(missing_ok=True)

    # -- 키

    def has_key(self) -> bool:
        return self.key_path.is_file()

    def read_key(self) -> str | None:
        """저장한 키를 푼다. 없거나 풀지 못하면 None(다른 사용자 계정이 저장한 파일 등)."""
        try:
            blob = self.key_path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            return None
        try:
            text = self.protector.unprotect(blob).decode("utf-8").strip()
        except Exception:  # 값은 찍지 않는다
            log.warning("저장한 유튜브 API 키를 풀지 못했습니다")
            return None
        return text or None

    def write_key(self, key: str) -> None:
        if not self.protector.available:
            raise SecretStoreUnavailable("이 PC에서는 키를 암호화해 저장할 수 없습니다")
        blob = self.protector.protect(key.encode("utf-8"))
        _atomic_write(self.key_path, blob)

    def delete_key(self) -> bool:
        existed = self.key_path.is_file()
        self.key_path.unlink(missing_ok=True)
        return existed

    # -- R5: AI별 API 키(유튜브 키와 같은 방식, 파일만 따로)

    def llm_key_path(self, name: str) -> Path:
        if not PROVIDER_NAME.match(name):
            raise ValueError("AI 이름이 잘못됐습니다")
        return self.root / LLM_KEY_DIR / f"{name}.bin"

    def has_llm_key(self, name: str) -> bool:
        return self.llm_key_path(name).is_file()

    def read_llm_key(self, name: str) -> str | None:
        try:
            blob = self.llm_key_path(name).read_bytes()
        except (FileNotFoundError, ValueError):
            return None
        except OSError:
            return None
        try:
            text = self.protector.unprotect(blob).decode("utf-8").strip()
        except Exception:  # 값은 찍지 않는다
            log.warning("저장한 AI API 키를 풀지 못했습니다(%s)", name)
            return None
        return text or None

    def write_llm_key(self, name: str, key: str) -> None:
        if not self.protector.available:
            raise SecretStoreUnavailable("이 PC에서는 키를 암호화해 저장할 수 없습니다")
        path = self.llm_key_path(name)
        _atomic_write(path, self.protector.protect(key.encode("utf-8")))

    def delete_llm_key(self, name: str) -> bool:
        path = self.llm_key_path(name)
        existed = path.is_file()
        path.unlink(missing_ok=True)
        return existed


def key_shape_ok(key: str) -> bool:
    """키 모양(영문·숫자·_-, 20~200자). 진짜인지는 [연결 확인]이 본다."""
    return bool(_KEY_SHAPE.match(key))


def llm_key_shape_ok(key: str) -> bool:
    """R5: AI 서비스 키 모양(빈칸 없는 글자 8~400자). 진짜인지는 [연결 확인]이 본다."""
    return bool(_LLM_KEY_SHAPE.match(key))


# ---------------------------------------------------------------- 칸 정의


@dataclass(frozen=True)
class Field:
    kind: str  # int | str | bool | choice | lines | models | urls(R5: AI 이름 → 글)
    label: str  # 화면 이름(오류 문구에 쓴다)
    path: tuple[str, ...] | None = None  # config.yaml 안의 자리(없으면 따로 다룬다)
    lo: int | None = None  # int: 최솟값, str·lines: 가장 짧은 길이
    hi: int | None = None  # int: 최댓값, str·lines: 가장 긴 길이
    choices: tuple[str, ...] = ()
    max_items: int = 0  # lines: 줄 수 한도


FIELDS: dict[str, Field] = {
    "llm.model": Field("str", "AI 모델", None, 1, 200),
    "comment.min_chars": Field("int", "최소 글자 수", ("comment", "min_chars"), 10, 500),
    "comment.max_chars": Field("int", "최대 글자 수", ("comment", "max_chars"), 20, 1000),
    "comment.brand": Field("str", "홍보하는 곳 이름", ("comment", "brand"), 1, 30),
    "brand.facts": Field("lines", "써도 되는 사실 문장", ("brand", "facts"), 2, 200, max_items=10),
    "comment.disclosure": Field("str", "광고 표기 문구", ("comment", "disclosure"), 1, 20),
    "comment.disclose_default": Field("bool", "광고 표기 기본값", ("comment", "disclose_default")),
    "comment.ai_review": Field("bool", "AI 검수 한 번", ("comment", "ai_review")),
    "comment.writer": Field(
        "choice", "댓글 쓰는 방식", ("comment", "writer"), choices=tuple(WRITER_LABELS)
    ),
    "limits.daily_max_comments": Field(
        "int", "하루 상한", ("limits", "daily_max_comments"), 1, 50
    ),
    "posting.confirm_before_post": Field(
        "bool", "게시 직전에 한 번 더 확인", ("posting", "confirm_before_post")
    ),
    "posting.after_post_window": Field(
        "choice", "게시 뒤 크롬 창", ("posting", "after_post_window"),
        choices=tuple(AFTER_POST_WINDOW_LABELS),
    ),
    "browser.typing_speed": Field(
        "choice", "글자 입력 속도", ("browser", "typing_speed"), choices=tuple(TYPING_SPEEDS)
    ),
    # 크롬 창을 띄울 화면: auto(「자동 (권장)」, 기본) 또는 모니터 ID(GET /api/screens). 모니터를
    # 고르면 그 모니터의 안전한 위치를 browser.window_position에도 넣는다(옛 판과 맞추려고. 좌표를
    # 직접 치지 않는다). auto는 그 좌표를 지운다
    "browser.window_screen": Field(
        "str", "크롬 창을 띄울 화면", ("browser", "window_screen"), 1, 60
    ),
    "browser.window_position": Field("str", "크롬 창 위치", ("browser", "window_position"), 3, 30),
    "discover.query": Field("str", "기본 검색어", ("discover", "query"), 1, 100),
    "discover.max_results": Field("int", "기본 개수", ("discover", "max_results"), 1, 50),
    "discover.exclude_shorts": Field("bool", "쇼츠 빼기", ("discover", "exclude_shorts")),
    "discover.shorts_under_seconds": Field(
        "int", "쇼츠로 볼 길이", ("discover", "shorts_under_seconds"), 10, 3600
    ),
    # R4: 자막 자동으로 읽기(기본 켬), 시작할 때 AI 모델 미리 불러오기(기본 켬), 뜨기 직전 영상 조건
    "transcript.auto": Field("bool", "자막 자동으로 읽기", ("transcript", "auto")),
    "llm.warmup_on_start": Field(
        "bool", "시작할 때 AI 모델 미리 불러오기", ("llm", "warmup_on_start")
    ),
    "rising.query": Field("str", "뜨기 직전 영상 검색어", ("rising", "query"), 1, 100),
    "rising.min_views": Field(
        "int", "뜨기 직전 최소 조회수", ("rising", "min_views"), 0, 1_000_000
    ),
    "rising.max_views": Field(
        "int", "뜨기 직전 최대 조회수", ("rising", "max_views"), 1, 10_000_000
    ),
    "rising.min_views_per_hour": Field(
        "int", "뜨기 직전 시간당 조회수", ("rising", "min_views_per_hour"), 1, 1_000_000
    ),
}
# R5: 글 쓰는 AI. 고를 수 있는 이름인지(설정의 llm.providers, 설치·키 여부)는 설정 API가 본다.
# llm.models·llm.base_urls는 AI 이름 → 모델·주소(보낸 이름만 바꾸고, 빈 글이면 지운다)
FIELDS["llm.active"] = Field("str", "글 쓰는 AI", ("llm", "active"), 1, 40)
FIELDS["llm.models"] = Field("models", "AI별 모델", None, 1, 200, max_items=20)
FIELDS["llm.base_urls"] = Field("urls", "직접 입력 주소", None, 8, 300, max_items=5)
# 2026-11-18: AI별 추론 수준(Codex). 이름은 app.llm.cli.REASONING_EFFORTS만
FIELDS["llm.reasoning"] = Field("reasoning", "AI별 추론 수준", None, 1, 20, max_items=20)
# 화면이 직접 보내지 않고 서버가 계산해 넣는 칸
COMPUTED_FIELDS = ("browser.window_position",)


def _clean_one(name: str, field: Field, value: Any) -> tuple[Any, str | None]:
    """값 하나를 정리한다. (정리한 값, 오류 문구 또는 None)."""
    label = field.label
    if field.kind == "bool":
        if isinstance(value, bool):
            return value, None
        return None, f"{label}은(는) 켬 또는 끔이어야 합니다"
    if field.kind == "int":
        if isinstance(value, bool):
            return None, f"{label}은(는) 숫자여야 합니다"
        try:
            num = int(str(value).strip())
        except (TypeError, ValueError):
            return None, f"{label}은(는) 숫자여야 합니다"
        if field.lo is not None and field.hi is not None and not field.lo <= num <= field.hi:
            return None, f"{label}은(는) {field.lo}~{field.hi} 사이여야 합니다"
        return num, None
    if field.kind == "choice":
        text = str(value or "").strip()
        if text not in field.choices:
            return None, f"{label}에서 고를 수 없는 값입니다"
        return text, None
    if field.kind in ("models", "urls", "reasoning"):
        if not isinstance(value, dict) or len(value) > field.max_items:
            return None, f"{label} 모양이 잘못됐습니다"
        out: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not PROVIDER_NAME.match(key):
                return None, f"{label}: 모르는 AI 이름입니다"
            if item is None:
                item = ""
            if not isinstance(item, str):
                return None, f"{label}은(는) 글로 적어 주세요"
            text = item.strip()
            if text and field.kind == "reasoning":
                from app.llm.cli import REASONING_EFFORTS

                if text not in REASONING_EFFORTS:
                    return None, f"{label}에서 고를 수 없는 값입니다: {text[:20]}"
            if text and field.kind == "models" and not MODEL_NAME.match(text):
                return None, "모델 이름은 영문·숫자로 시작하고 빈칸 없이 200자까지입니다"
            too_long = len(text) > (field.hi or 300)
            if text and field.kind == "urls" and (too_long or not _URL.match(text)):
                return None, "주소는 http:// 또는 https://로 시작해야 합니다(예: http://127.0.0.1:1234/v1)"
            out[key] = text.rstrip("/") if field.kind == "urls" else text
        return out, None
    if field.kind == "lines":
        if not isinstance(value, list):
            return None, f"{label}은(는) 문장 목록이어야 합니다"
        lines = [" ".join(str(v).split()) for v in value]
        lines = [t for t in lines if t]
        if len(lines) > field.max_items:
            return None, f"{label}은(는) {field.max_items}줄까지 쓸 수 있습니다"
        for t in lines:
            if field.lo and len(t) < field.lo:
                return None, f"{label}의 한 줄이 너무 짧습니다({field.lo}자 이상)"
            if field.hi and len(t) > field.hi:
                return None, f"{label}의 한 줄은 {field.hi}자까지입니다"
        return lines, None
    # str
    if value is None or isinstance(value, (dict, list, bool)):
        return None, f"{label}을(를) 글로 적어 주세요"
    text = " ".join(str(value).split())
    if field.lo and len(text) < field.lo:
        return None, f"{label}을(를) 비워 둘 수 없습니다"
    if field.hi and len(text) > field.hi:
        return None, f"{label}은(는) {field.hi}자까지입니다"
    return text, None


def validate(
    changes: dict[str, Any], current: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """바꾸려는 값(`changes`)을 정리하고 검사한다. (정리한 값, 칸 이름 → 이유).

    `current`는 지금 쓰는 값 전부(바꾸지 않는 칸과 함께 보는 검사 — 최소 < 최대 — 에 쓴다).
    """
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, value in changes.items():
        field = FIELDS.get(name)
        if field is None or name in COMPUTED_FIELDS:
            errors[name] = "바꿀 수 없는 칸입니다"
            continue
        out, problem = _clean_one(name, field, value)
        if problem:
            errors[name] = problem
        else:
            clean[name] = out
    merged = {**current, **clean}
    lo, hi = merged.get("comment.min_chars"), merged.get("comment.max_chars")
    if isinstance(lo, int) and isinstance(hi, int) and lo >= hi:
        where = "comment.min_chars" if "comment.min_chars" in clean else "comment.max_chars"
        errors.setdefault(where, "최소 글자 수가 최대 글자 수보다 커서는 안 됩니다(최소 < 최대)")
    rlo, rhi = merged.get("rising.min_views"), merged.get("rising.max_views")
    if isinstance(rlo, int) and isinstance(rhi, int) and rlo > rhi:
        where = "rising.min_views" if "rising.min_views" in clean else "rising.max_views"
        errors.setdefault(where, "최소 조회수가 최대 조회수보다 커서는 안 됩니다")
    disclosure = merged.get("comment.disclosure")
    if isinstance(disclosure, str) and isinstance(hi, int) and len(disclosure) + 10 > hi:
        where = "comment.disclosure" if "comment.disclosure" in clean else "comment.max_chars"
        errors.setdefault(where, "광고 표기 문구가 최대 글자 수에 비해 너무 깁니다")
    return clean, errors


def apply_overlay(rules: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """`config.yaml` 내용에 사용자가 바꾼 값을 덮은 사본. 원본은 바꾸지 않는다."""
    out = copy.deepcopy(rules)
    for name, value in values.items():
        field = FIELDS.get(name)
        if field is None or field.path is None:
            continue
        node = out
        for part in field.path[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[field.path[-1]] = copy.deepcopy(value)
        if name == "browser.typing_speed" and value in TYPING_SPEEDS:
            out.setdefault("browser", {})["typing_delay_ms"] = list(TYPING_SPEEDS[value])
        if name == "posting.after_post_window" and value in AFTER_POST_WINDOW_LABELS:
            out["posting"]["keep_window_seconds"] = (
                keep_seconds_of(rules) if value == "keep" else 0
            )
    return out


def keep_seconds_of(rules: dict[str, Any]) -> int:
    """「열어 두기」의 초: config.yaml의 `posting.keep_window_seconds`가 0보다 크면 그 값,
    아니면 300."""
    posting = rules.get("posting") if isinstance(rules.get("posting"), dict) else {}
    value = posting.get("keep_window_seconds")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return KEEP_WINDOW_DEFAULT_SECONDS


def after_post_window_of(seconds: int) -> str:
    """설정 화면의 값: 0초면 「바로 닫기」, 아니면 「열어 두기」."""
    return "keep" if seconds > 0 else "close"


def typing_speed_of(delay: tuple[int, int]) -> str:
    """입력 속도 이름. 정해 둔 셋과 다르면 가운데 값이 가장 가까운 것."""
    for name, pair in TYPING_SPEEDS.items():
        if tuple(delay) == pair:
            return name
    mid = (delay[0] + delay[1]) / 2
    return min(TYPING_SPEEDS, key=lambda n: abs(sum(TYPING_SPEEDS[n]) / 2 - mid))
