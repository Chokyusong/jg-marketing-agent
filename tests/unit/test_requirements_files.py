"""requirements 파일을 새 PC의 pip가 읽을 수 있다(2026-11-17, 새 폴더에 내려받아 설치해 본 결과).

한국어 Windows에서 pip 24.3.1은 BOM이 없는 파일을 PC 기본 글자 체계(cp949)로 읽는다. 한글 설명 줄이
UTF-8이면 `UnicodeDecodeError`로 설치가 멈춘다. pip는 맨 앞 두 줄의 `coding: utf-8` 표시를 따르므로,
ASCII가 아닌 파일은 그 표시가 있어야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted(ROOT.glob("requirements*.txt"))
CODING = re.compile(rb"coding[:=]\s*utf-?8", re.IGNORECASE)


def test_requirements_files_exist():
    assert {p.name for p in FILES} >= {"requirements.txt", "requirements-dev.txt"}


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_non_ascii_requirements_declare_utf8_in_first_two_lines(path: Path):
    raw = path.read_bytes()
    try:
        raw.decode("ascii")
    except UnicodeDecodeError:
        head = b"\n".join(raw.splitlines()[:2])
        assert CODING.search(head), f"{path.name}: 맨 앞 두 줄에 coding: utf-8 표시가 필요합니다"
    raw.decode("utf-8")  # 표시대로 읽힌다
