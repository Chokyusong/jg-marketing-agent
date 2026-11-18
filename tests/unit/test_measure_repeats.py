"""`scripts/measure_repeats.py` — 여러 영상 초안의 되풀이를 재는 스크립트(생성에는 쓰지 않는다)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_repeats as M  # noqa: E402

SAME = [
    {"video_id": "a", "body": "[광고] 답장 늦는 장면 보니 속상하네요. 운명원이 연애 사주 잘 "
                              "본다던데 한번 보고 싶네요."},
    {"video_id": "b", "body": "[광고] 계정 몰래 보는 얘기에 뜨끔했어요. 운명원이 연애 사주 잘 "
                              "본다던데 한번 보고 싶네요."},
]
OTHER = {"video_id": "c", "body": "[광고] 사진 200장 지우는 게 제일 어렵다는 말 공감돼요ㅠㅠ "
                                  "요즘 다들 운명원 가서 연애사주 본다는데 저도 가 볼까 봐요"}


def test_same_brand_sentence_and_ending_are_counted():
    r = M.measure([*SAME, OTHER])
    assert r["n"] == 3
    assert r["words"]["잘 본다던데"] == 2 and r["words"]["한번"] == 2 and r["words"]["저도"] == 1
    assert r["brand_groups"][0] == [1, 2] and r["brand_kinds"] == 2
    assert r["top_end"] == "싶네요" and r["top_end_ratio"] == round(2 / 3, 2)
    assert r["top_end2"] == "보고 싶네요"
    # 다른 영상 쌍 셋 중 a–b만 어절 4개가 잇달아 겹친다 — 운명원 문장 밖에서는 겹치지 않는다
    assert r["cross_pairs"] == 3 and [(i, j) for i, j, _ in r["shared4"]] == [(1, 2)]
    assert r["shared4_rest"] == []
    assert dict(r["openings"])["~보니"] == 1


def test_required_words_alone_do_not_make_one_shape():
    # 브랜드·연애·사주는 꼭 들어가는 말이라 그것만 같으면 다른 꼴이다
    a = "운명원이 연애 사주 잘 본다던데 재회운 볼까 봐요"
    b = "요즘 운명원 연애사주가 유명하길래 제 짝은 어떤 사람일지 궁금해요"
    assert len(M.groups([a, b], skip=("운명원", "연애", "사주"))) == 2


def test_same_video_pairs_are_not_counted_and_files_load(tmp_path):
    two = [{"video_id": "a", "body": SAME[0]["body"]}, {"video_id": "a", "body": SAME[0]["body"]}]
    assert M.measure(two)["cross_pairs"] == 0
    run = {"videos": [{"video_id": "a", "drafts": [{"body": SAME[0]["body"]}]},
                      {"video_id": "b", "drafts": [{"body": SAME[1]["body"]}]}]}
    path = tmp_path / "run.json"
    path.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    flat = tmp_path / "flat.json"
    flat.write_text(json.dumps([OTHER], ensure_ascii=False), encoding="utf-8")
    loaded = M.load([path, flat])
    assert [d["video_id"] for d in loaded] == ["a", "b", "c"]
    out = tmp_path / "out.md"
    assert M.main([str(path), "--before", str(flat), "--out-md", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "| | 지난 판 | 이번 판 |" in text and "운명원 문장 꼴 수" in text
