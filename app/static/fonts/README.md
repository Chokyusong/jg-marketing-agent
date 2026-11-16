# 글꼴

화면 제목에 쓰는 명조 글꼴이다. 인터넷 없이도 목업과 같은 모습이 나오도록 프로그램에 넣었다.

| 항목 | 내용 |
|---|---|
| 글꼴 | Noto Serif KR |
| 저작권 | (c) 2017-2024 Adobe (http://www.adobe.com/). / Copyright 2012 Google Inc. |
| 라이선스 | SIL Open Font License 1.1 — 전문은 같은 폴더 [`OFL.txt`](OFL.txt) |
| 원본 | Google Fonts 저장소 `google/fonts`의 `ofl/notoserifkr/NotoSerifKR[wght].ttf` (2026-11-16에 받음, 그 폴더의 마지막 변경 커밋 `8b0a1d0f`) |
| 원본의 원본 | `notofonts/noto-cjk` |

## 이 파일은 원본을 고친 것이다

`NotoSerifKR-Regular-subset.woff2`는 원본 가변 글꼴(약 23.8MB)에서

1. 굵기 400만 뽑고
2. 한글, 기본 영문·숫자·기호, 자주 쓰는 문장부호만 남기고
3. WOFF2로 압축한 파일이다(약 1MB).

만든 방법은 [`scripts/subset_font.py`](../../../scripts/subset_font.py)에 있다(`fonttools`, `brotli` 필요).

## 라이선스 조건과 지킨 방법

- 글꼴만 따로 팔지 않는다 → 프로그램에 함께 넣어 무료로 배포한다.
- 저작권 표시와 라이선스를 함께 배포한다 → `OFL.txt`와 이 문서를 같은 폴더에 둔다.
- 고친 글꼴도 같은 라이선스를 따른다 → 이 파일도 SIL OFL 1.1이다.
- 예약된 글꼴 이름(Reserved Font Name)은 이 글꼴의 `OFL.txt`에 지정돼 있지 않다.

## 쓰는 법

템플릿에서 `/static/fonts/fonts.css`를 불러오고, 제목 글꼴 순서 맨 앞에 `"Noto Serif KR"`를 둔다.
굵기는 400 하나뿐이다. 본문 글꼴은 넣지 않았다(PC에 있는 맑은 고딕 등을 쓴다).
