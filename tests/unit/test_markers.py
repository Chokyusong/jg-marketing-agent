"""live·e2e 표시가 의도대로 건너뛰어지는지 확인한다(conftest를 복사한 별도 pytest 실행)."""

from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"

SAMPLE_TESTS = """
import pytest

def test_plain():
    pass

@pytest.mark.live
def test_live():
    pass

@pytest.mark.e2e
def test_e2e():
    pass
"""


def make_sample(pytester: pytest.Pytester, *, playwright: bool) -> pytest.Pytester:
    source = CONFTEST.read_text(encoding="utf-8").replace('pytest_plugins = ["pytester"]', "")
    # Playwright 설치 여부를 흉내 낸다(모듈 끝에서 다시 정의하면 이 정의가 쓰인다).
    source += f"\n\ndef playwright_available() -> bool:\n    return {playwright}\n"
    pytester.makeconftest(source)
    pytester.makepyfile(test_sample=SAMPLE_TESTS)
    return pytester


def test_live_and_e2e_skipped_by_default(pytester, monkeypatch):
    monkeypatch.delenv("RUN_LIVE", raising=False)
    result = make_sample(pytester, playwright=False).runpytest("-p", "no:cacheprovider", "-rs")
    result.assert_outcomes(passed=1, skipped=2)
    result.stdout.fnmatch_lines(["*RUN_LIVE=1*", "*playwright*"])


def test_live_runs_with_run_live(pytester, monkeypatch):
    monkeypatch.setenv("RUN_LIVE", "1")
    result = make_sample(pytester, playwright=False).runpytest("-p", "no:cacheprovider")
    result.assert_outcomes(passed=2, skipped=1)


def test_e2e_runs_when_playwright_present(pytester, monkeypatch):
    monkeypatch.delenv("RUN_LIVE", raising=False)
    result = make_sample(pytester, playwright=True).runpytest("-p", "no:cacheprovider")
    result.assert_outcomes(passed=2, skipped=1)
