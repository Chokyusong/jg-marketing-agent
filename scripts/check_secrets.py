"""커밋 대상 파일에서 비밀값과 커밋하면 안 되는 파일을 찾는다. 표준 라이브러리만 쓴다.

사용법:
    python scripts/check_secrets.py            # 스테이징된 파일 (pre-commit 훅 기본)
    python scripts/check_secrets.py --staged   # 위와 같음
    python scripts/check_secrets.py --all      # git이 추적하는 파일 전체
    python scripts/check_secrets.py 경로 ...    # 지정한 파일

찾은 것이 있으면 종료 코드 1. 찾은 값 자체는 출력하지 않는다(앞 몇 글자만).
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

CONTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Google API 키", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("GitHub 토큰", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    ("GitHub 세분화 토큰", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("OpenAI·Anthropic 키", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b")),
    ("Slack 토큰", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    ("AWS 접근 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "개인키 블록",
        re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----"),
    ),
]

# 경로만으로 막는 파일 (내용과 무관)
FORBIDDEN_PATH_GLOBS: list[tuple[str, str]] = [
    ("*.db", "SQLite DB"),
    ("*.sqlite3", "SQLite DB"),
    ("*.pdf", "PDF(과제 원문 등 회사 자료)"),
    ("*.pem", "인증서·키 파일"),
    ("*.key", "키 파일"),
    ("*.p12", "인증서·키 파일"),
    ("*.pfx", "인증서·키 파일"),
    ("id_rsa*", "SSH 키"),
    ("id_ed25519*", "SSH 키"),
]
FORBIDDEN_DIR_NAMES = {"profiles": "브라우저 프로필 폴더", "error_screenshots": "실패 화면 캡처"}

# .env.example에서 값이 비어 있어야 하는 이름
SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)
ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


@dataclass
class Finding:
    path: str
    line: int
    kind: str
    hint: str = ""

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        extra = f" ({self.hint})" if self.hint else ""
        return f"  {where}: {self.kind}{extra}"


def _mask(value: str) -> str:
    return value[:4] + "..." if len(value) > 4 else "..."


def is_env_file(name: str) -> bool:
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def check_path(path: str) -> list[Finding]:
    p = PurePosixPath(path.replace("\\", "/"))
    findings: list[Finding] = []
    if is_env_file(p.name):
        findings.append(Finding(path, 0, ".env 파일", "비밀값 파일은 커밋하지 않는다"))
    for glob, label in FORBIDDEN_PATH_GLOBS:
        if fnmatch.fnmatch(p.name.lower(), glob):
            findings.append(Finding(path, 0, label, "커밋 금지 파일"))
    for part in p.parts[:-1]:
        if part in FORBIDDEN_DIR_NAMES:
            findings.append(Finding(path, 0, FORBIDDEN_DIR_NAMES[part], "커밋 금지 폴더"))
    return findings


def check_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    name = PurePosixPath(path.replace("\\", "/")).name
    check_env_values = name == ".env.example"
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in CONTENT_PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append(Finding(path, lineno, kind, _mask(m.group(0))))
        if check_env_values:
            m = ENV_LINE.match(line)
            if m and SECRET_NAME.search(m.group(1)):
                value = m.group(2).split("#", 1)[0].strip().strip("'\"")
                if value:
                    findings.append(
                        Finding(path, lineno, f".env.example에 {m.group(1)} 값이 채워짐")
                    )
    return findings


def decode(data: bytes) -> str | None:
    if b"\x00" in data[:8192]:
        return None  # 바이너리
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="ignore")


def check_file(path: str, data: bytes | None) -> list[Finding]:
    findings = check_path(path)
    if data is not None:
        text = decode(data)
        if text is not None:
            findings.extend(check_text(path, text))
    return findings


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def staged_files() -> list[tuple[str, bytes | None]]:
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    result = []
    for path in filter(None, out.decode("utf-8").split("\0")):
        try:
            data = _git("show", f":{path}")
        except subprocess.CalledProcessError:
            data = None
        result.append((path, data))
    return result


def tracked_files() -> list[tuple[str, bytes | None]]:
    out = _git("ls-files", "-z")
    result = []
    for path in filter(None, out.decode("utf-8").split("\0")):
        fp = Path(path)
        result.append((path, fp.read_bytes() if fp.is_file() else None))
    return result


def given_files(paths: list[str]) -> list[tuple[str, bytes | None]]:
    result = []
    for path in paths:
        fp = Path(path)
        result.append((path, fp.read_bytes() if fp.is_file() else None))
    return result


def scan(files: list[tuple[str, bytes | None]]) -> list[Finding]:
    findings: list[Finding] = []
    for path, data in files:
        findings.extend(check_file(path, data))
    return findings


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="비밀값·커밋 금지 파일 검사")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="스테이징된 파일 검사(기본)")
    group.add_argument("--all", action="store_true", help="git 추적 파일 전체 검사")
    parser.add_argument("paths", nargs="*", help="검사할 파일")
    args = parser.parse_args(argv)

    if args.paths:
        files = given_files(args.paths)
        scope = "지정한 파일"
    elif args.all:
        files = tracked_files()
        scope = "추적 파일 전체"
    else:
        files = staged_files()
        scope = "스테이징된 파일"

    findings = scan(files)
    if findings:
        print(
            f"[check_secrets] 실패: {scope} {len(files)}개 중 {len(findings)}건 발견",
            file=sys.stderr,
        )
        for f in findings:
            print(str(f), file=sys.stderr)
        print("  비밀값을 지우고 .env로 옮긴 뒤 다시 커밋한다.", file=sys.stderr)
        return 1
    print(f"[check_secrets] 통과: {scope} {len(files)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
