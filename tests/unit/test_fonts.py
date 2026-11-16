"""화면에 넣은 글꼴 파일이 라이선스와 함께 제대로 들어 있는지 확인한다."""

import re
from pathlib import Path

FONTS = Path(__file__).resolve().parents[2] / "app" / "static" / "fonts"
WOFF2 = FONTS / "NotoSerifKR-Regular-subset.woff2"


def test_font_file_is_woff2_and_small():
    data = WOFF2.read_bytes()
    assert data[:4] == b"wOF2"
    # 필요한 글자만 남긴 파일이어야 한다. 원본(약 24MB)을 통째로 넣으면 실패한다.
    assert len(data) < 2_000_000


def test_license_ships_with_font():
    text = (FONTS / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in text
    readme = (FONTS / "README.md").read_text(encoding="utf-8")
    assert "Noto Serif KR" in readme
    assert "OFL.txt" in readme


def test_font_css_points_to_existing_file():
    css = (FONTS / "fonts.css").read_text(encoding="utf-8")
    urls = re.findall(r'url\("([^"]+)"\)', css)
    assert urls, "fonts.css에 글꼴 주소가 없다"
    for url in urls:
        assert not url.startswith(("http:", "https:", "//")), "글꼴을 외부에서 내려받으면 안 된다"
        assert (FONTS / url).is_file()
