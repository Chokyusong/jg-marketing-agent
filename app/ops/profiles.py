"""프로필 목록과 자동 배정(DESIGN 6.3 · PLAYBOOK 7단계).

- 화면에 보이는 이름은 `config.yaml`의 `profiles`(유튜브1·2·3), 폴더 이름은 순서대로 영문
  `profile-1`, `profile-2`…(한글 폴더 이름의 경로 문제를 피한다). 폴더가 놓일 곳
  (`%LOCALAPPDATA%\\JGMarketingAgent\\profiles\\`)과 실제 크롬 실행은 8단계 몫이다.
  API와 화면에는 폴더 이름만 보이고 PC의 전체 경로는 싣지 않는다.
- 자동 배정(`pick_auto`)은 그 대상(sandbox·youtube)에서 **가장 오래 안 쓴 프로필**을 고른다.
  한 번도 안 쓴 프로필이 먼저(설정 순서대로), 다음은 마지막으로 쓴 시각이 가장 이른 것.
  "썼다"는 그 프로필로 예약한 적이 있다는 뜻이다(`posts.updated_at`, 실패도 포함). 시각이 같으면
  나중에 넣은 예약(id가 큰 것)을 더 최근으로 본다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app import db
from app.errors import AppError, ErrorKind
from app.ops.rules import check_target


@dataclass(frozen=True)
class Profile:
    name: str  # 화면 이름(유튜브1)
    folder: str  # 폴더 이름(profile-1)
    index: int  # 1부터


def folder_name(index: int) -> str:
    return f"profile-{index}"


class ProfileService:
    def __init__(self, names: Sequence[str], *, db_path: Path) -> None:
        self.db_path = db_path
        self._profiles = tuple(
            Profile(name=n, folder=folder_name(i), index=i) for i, n in enumerate(names, start=1)
        )

    def list_profiles(self) -> list[Profile]:
        return list(self._profiles)

    def names(self) -> list[str]:
        return [p.name for p in self._profiles]

    def get(self, name: str) -> Profile:
        for p in self._profiles:
            if p.name == name:
                return p
        raise AppError(ErrorKind.PROFILE_UNKNOWN, detail=f"프로필 {name!r}")

    def folder_of(self, name: str) -> str:
        return self.get(name).folder

    def last_used(self, target: str) -> dict[str, str]:
        """그 대상에서 프로필마다 마지막으로 쓴 시각(쓴 적 없는 프로필은 빠진다)."""
        return {name: at for name, (at, _) in self._usage(target).items()}

    def _usage(self, target: str) -> dict[str, tuple[str, int]]:
        check_target(target)
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT profile, MAX(updated_at) AS at, MAX(id) AS last_id FROM posts "
                "WHERE target=? GROUP BY profile",
                (target,),
            ).fetchall()
        return {r["profile"]: (r["at"], int(r["last_id"])) for r in rows}

    def pick_auto(self, target: str) -> Profile:
        """가장 오래 안 쓴 프로필. 셋을 차례로 돈다(유튜브1 → 2 → 3 → 1 …)."""
        if not self._profiles:
            raise AppError(ErrorKind.PROFILE_UNKNOWN, detail="profiles가 비어 있음")
        used = self._usage(target)
        never = [p for p in self._profiles if p.name not in used]
        if never:
            return never[0]
        return min(self._profiles, key=lambda p: (*used[p.name], p.index))

    def resolve(self, name: str | None, target: str) -> Profile:
        """화면에서 고른 이름. 비었거나 「자동 배정」이면 `pick_auto`."""
        if not name or name == "auto":
            return self.pick_auto(target)
        return self.get(name)
