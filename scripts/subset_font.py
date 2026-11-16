"""Noto Serif KR 가변 글꼴에서 굵기 400만 뽑고 필요한 글자만 남겨 WOFF2로 저장한다.

app/static/fonts/NotoSerifKR-Regular-subset.woff2를 다시 만들 때만 쓴다.
앱 실행이나 테스트에는 필요 없다. 따로 설치: pip install fonttools brotli

사용: python scripts/subset_font.py <원본 NotoSerifKR[wght].ttf> <결과.woff2>
원본: https://github.com/google/fonts/tree/main/ofl/notoserifkr (SIL OFL 1.1)
"""

import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

EXTRA = "·…—–‘’“”「」『』〈〉《》※→←↑↓↗↘×÷±°₩•‧〃ㆍ％＆（）［］"
SAMPLE = "영상을 이해하고, 다음 행동을 설계합니다. 작업 기록 0123456789 JG /"


def wanted_codepoints() -> list[int]:
    chars = set(range(0x20, 0x7F))  # 기본 영문·숫자·기호
    chars |= set(range(0x3131, 0x318F))  # 한글 낱자
    for cp in range(0xAC00, 0xD7A4):  # KS X 1001 완성형 2,350자
        try:
            chr(cp).encode("euc_kr")
        except UnicodeEncodeError:
            continue
        chars.add(cp)
    chars |= {ord(c) for c in EXTRA}
    return sorted(chars)


def main(src: str, out: str) -> None:
    font = instancer.instantiateVariableFont(TTFont(src), {"wght": 400})
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]  # 저작권·라이선스 표기를 글꼴 안에 그대로 둔다
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    subsetter = subset.Subsetter(opts)
    subsetter.populate(unicodes=wanted_codepoints())
    subsetter.subset(font)
    font.flavor = "woff2"
    font.save(out)

    cmap = TTFont(out).getBestCmap()
    hangul = sum(1 for cp in cmap if 0xAC00 <= cp <= 0xD7A3)
    missing = sorted({c for c in SAMPLE if c != " " and ord(c) not in cmap})
    print(f"codepoints={len(cmap)} hangul={hangul} missing={missing}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
