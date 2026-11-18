"""여러 영상의 초안이 같은 꼴을 되풀이하는지 숫자로 잰다(2026-11-18 대표: 점수보다 22개를 나란히
놓고 문장 구조와 결말이 되풀이되는지 본다). 재기만 한다 — 생성·검사에는 쓰지 않는다.

    .\\.venv\\Scripts\\python.exe scripts\\measure_repeats.py run1.json run2.json --label 새 판 ^
        --before old.json --before-label 지난 판 --out-md out.md --out-json out.json

입력: `scripts/compare_drafts.py`의 `--out-json`(영상마다 초안 목록) 또는 초안 목록 JSON.

잰 것
- 낱말: 「인연」「궁합」「한번」「보고 싶」「잘 본다던데」「저도」「저라도」「유명」「궁금」
  「이런」이 든 글 수
  (띄어쓰기 무시)
- 운명원 문장: 브랜드가 든 문장을 뽑아, 꼭 들어가는 말(브랜드·연애·사주가 든 어절)을 빼고 같은
  어절이 3개 이상이면 같은 꼴로 묶은 꼴 수(묶음의 첫 문장과 견준다 — 사슬처럼 잇지 않는다)
- 맨 끝 어절(서술어)·맨 끝 두 어절 종류와 가장 많은 것의 비율
- 서로 다른 영상의 초안 쌍 중 같은 어절 4개가 잇달아 겹치는 쌍 수(글 전체, 그리고 운명원
  문장을 뺀 나머지)
- 첫 문장 꼴(「~라니」「~보니」「저라도 ~」「저도 ~」 …) 분포
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

WORDS = ("인연", "궁합", "한번", "보고 싶", "잘 본다던데", "저도", "저라도", "유명", "궁금", "이런")
STRIP = re.compile(r"[^\w가-힣]")


def load(paths: Sequence[str | Path]) -> list[dict[str, str]]:
    """compare_drafts 결과 또는 초안 목록에서 (video_id, body)만 꺼낸다."""
    out: list[dict[str, str]] = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for video in data.get("videos", []):
                for d in video.get("drafts", []):
                    out.append({"video_id": d.get("video_id") or video["video_id"],
                                "body": d["body"]})
        else:
            out += [{"video_id": d["video_id"], "body": d["body"]} for d in data]
    return out


def body_of(text: str, disclosure: str = "[광고]") -> str:
    text = text.strip()
    if text.startswith(disclosure):
        text = text[len(disclosure):]
    return " ".join(text.split())


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?~])\s+|(?<=[ㅠㅜㅋ^])\s+|\.\.+\s*", text)]
    return [p for p in parts if p]


def eojeols(text: str) -> list[str]:
    words = [STRIP.sub("", w) for w in text.split()]
    return [w for w in words if w]


def last_word(text: str) -> str:
    words = [re.sub(r"[ㅋㅠㅜ^]+$", "", w) for w in eojeols(text)]
    words = [w for w in words if w]
    return words[-1] if words else ""


def opening(first: str) -> str:
    """첫 문장의 꼴(대략). 고정된 갈래가 아니라 눈으로 보기 쉬우라는 이름이다."""
    s = first.replace(" ", "")
    if s.startswith("저라도"):
        return "저라도 ~"
    if s.startswith("저도"):
        return "저도 ~"
    for mark, name in (("라니", "~라니"), ("다니", "~다니"), ("보니", "~보니"),
                       ("는거", "~는 거"), ("는게", "~는 게"), ("는말", "~는 말에"),
                       ("장면", "~장면")):
        if mark in s:
            return name
    return "그 밖: " + last_word(first)


def groups(items: Sequence[str], *, skip: Sequence[str] = (),
           min_shared: int = 3) -> list[list[int]]:
    """같은 어절이 `min_shared`개 이상이면 같은 꼴로 묶는다. 묶음의 첫 문장과만 견준다(사슬로
    이어 전부 한 묶음이 되지 않게). `skip`이 든 어절(꼭 들어가는 말)은 세지 않는다."""
    sets = [{w for w in eojeols(t) if not any(k in w for k in skip)} for t in items]
    found: list[list[int]] = []
    for i in range(len(items)):
        for g in found:
            if len(sets[i] & sets[g[0]]) >= min_shared:
                g.append(i)
                break
        else:
            found.append([i])
    return sorted(found, key=lambda g: (-len(g), g[0]))


def ngrams(words: Sequence[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[k:k + n]) for k in range(len(words) - n + 1)}


def measure(drafts: Sequence[dict[str, str]], *, brand: str = "운명원",
            disclosure: str = "[광고]") -> dict[str, Any]:
    bodies = [body_of(d["body"], disclosure) for d in drafts]
    flat = [b.replace(" ", "") for b in bodies]
    words = {w: sum(1 for b in flat if w.replace(" ", "") in b) for w in WORDS}
    brand_lines = []
    for k, b in enumerate(bodies, 1):
        hit = [s for s in sentences(b) if brand in s]
        brand_lines.append((k, hit[0] if hit else ""))
    texts = [t for _, t in brand_lines]
    skip = (brand, "연애", "사주")
    brand_groups = [[brand_lines[i][0] for i in g] for g in groups(texts, skip=skip)]
    ends = Counter(last_word(b) for b in bodies)
    ends2 = Counter(" ".join(eojeols(b)[-2:]) for b in bodies)
    top2, top2_n = ends2.most_common(1)[0] if ends2 else ("", 0)
    top_end, top_n = ends.most_common(1)[0] if ends else ("", 0)
    grams = [ngrams(eojeols(b), 4) for b in bodies]
    rest = [ngrams(eojeols(" ".join(s for s in sentences(b) if brand not in s)), 4)
            for b in bodies]
    cross = [(i, j) for i, j in itertools.combinations(range(len(bodies)), 2)
             if drafts[i]["video_id"] != drafts[j]["video_id"]]
    shared = [(i + 1, j + 1, " ".join(sorted(grams[i] & grams[j])[0]))
              for i, j in cross if grams[i] & grams[j]]
    shared_rest = [(i + 1, j + 1, " ".join(sorted(rest[i] & rest[j])[0]))
                   for i, j in cross if rest[i] & rest[j]]
    openings = Counter(opening(sentences(b)[0] if sentences(b) else b) for b in bodies)
    return {
        "n": len(bodies), "words": words, "brand_lines": brand_lines,
        "brand_groups": brand_groups, "brand_kinds": len(brand_groups),
        "ends": ends.most_common(), "top_end": top_end,
        "top_end_ratio": round(top_n / len(bodies), 2) if bodies else 0.0,
        "ends2": ends2.most_common(), "top_end2": top2,
        "top_end2_ratio": round(top2_n / len(bodies), 2) if bodies else 0.0,
        "cross_pairs": len(cross), "shared4": shared, "shared4_rest": shared_rest,
        "openings": openings.most_common(),
    }


def table(results: Sequence[tuple[str, dict[str, Any]]]) -> str:
    """판끼리 나란히 놓은 마크다운."""
    names = [name for name, _ in results]
    lines = ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]

    def row(label: str, values: Iterable[Any]) -> None:
        lines.append(f"| {label} | " + " | ".join(str(v) for v in values) + " |")

    row("초안 수", (r["n"] for _, r in results))
    for w in WORDS:
        row(f"「{w}」 든 글", (r["words"][w] for _, r in results))
    row("운명원 문장 꼴 수(꼭 든 말 빼고 어절 3개 이상 같으면 한 꼴)",
        (r["brand_kinds"] for _, r in results))
    row("가장 큰 운명원 문장 묶음", (len(r["brand_groups"][0]) if r["brand_groups"] else 0
                                    for _, r in results))
    row("맨 끝 어절 종류", (len(r["ends"]) for _, r in results))
    row("가장 많은 맨 끝 어절(비율)", (f"{r['top_end']} ({r['top_end_ratio']:.0%})"
                                      for _, r in results))
    row("맨 끝 두 어절 종류", (len(r["ends2"]) for _, r in results))
    row("가장 많은 맨 끝 두 어절(비율)", (f"{r['top_end2']} ({r['top_end2_ratio']:.0%})"
                                         for _, r in results))
    row("다른 영상 쌍 중 어절 4개 연속 겹침", (f"{len(r['shared4'])}/{r['cross_pairs']}"
                                              for _, r in results))
    row("— 운명원 문장을 뺀 나머지에서", (f"{len(r['shared4_rest'])}/{r['cross_pairs']}"
                                         for _, r in results))
    out = ["\n".join(lines)]
    for name, r in results:
        out.append(f"\n#### {name} — 운명원 문장\n")
        out.append("| # | 운명원 문장 | 묶음 |\n|---|---|---|")
        where = {k: g for g, ks in enumerate(r["brand_groups"], 1) for k in ks}
        size = {g: len(ks) for g, ks in enumerate(r["brand_groups"], 1)}
        for k, t in r["brand_lines"]:
            g = where.get(k, 0)
            out.append(f"| {k} | {t.replace('|', '／')} | {g}({size.get(g, 0)}개) |")
        out.append("\n- 맨 끝 어절: " + ", ".join(f"{w} {c}" for w, c in r["ends"]))
        out.append("- 맨 끝 두 어절: " + ", ".join(f"{w} {c}" for w, c in r["ends2"]))
        out.append("- 첫 문장 꼴: " + ", ".join(f"{w} {c}" for w, c in r["openings"]))
        pairs = ", ".join(f"#{i}–#{j}「{g}」" for i, j, g in r["shared4"][:12])
        out.append(f"- 어절 4개 연속 겹침(앞 12쌍): {pairs or '없음'}")
        rest = ", ".join(f"#{i}–#{j}「{g}」" for i, j, g in r["shared4_rest"])
        out.append(f"- 운명원 문장 밖에서 겹친 쌍: {rest or '없음'}")
    return "\n".join(out) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+", help="이번 판 JSON(여럿이면 합친다)")
    ap.add_argument("--label", default="이번 판")
    ap.add_argument("--before", nargs="*", default=[], help="견줄 판 JSON")
    ap.add_argument("--before-label", default="지난 판")
    ap.add_argument("--brand", default="운명원")
    ap.add_argument("--out-md")
    ap.add_argument("--out-json")
    args = ap.parse_args(argv)
    results = []
    if args.before:
        results.append((args.before_label, measure(load(args.before), brand=args.brand)))
    results.append((args.label, measure(load(args.runs), brand=args.brand)))
    md = table(results)
    if args.out_md:
        Path(args.out_md).write_text(md, encoding="utf-8")
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(dict(results), ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
