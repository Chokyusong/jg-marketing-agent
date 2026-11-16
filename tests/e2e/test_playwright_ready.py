"""e2e 준비 확인: Playwright를 불러올 수 있다(8단계부터 requirements.txt에 들어 있다).

e2e 테스트의 브라우저는 항상 headless로 띄운다(주 모니터에 창을 띄우지 않는다).
"""

import pytest


@pytest.mark.e2e
def test_playwright_importable():
    import playwright.sync_api  # noqa: F401
