"""프로필 목록과 자동 배정(DESIGN 6.3 · PLAYBOOK 7단계).

- 화면에 보이는 이름은 `config.yaml`의 `profiles`(유튜브1·2·3), 폴더 이름은 순서대로 영문
  `profile-1`, `profile-2`…(한글 폴더 이름의 경로 문제를 피한다). 폴더가 놓일 곳
  (`%LOCALAPPDATA%\\JGMarketingAgent\\profiles\\`)과 실제 크롬 실행은 8단계 몫이다.
  API와 화면에는 폴더 이름만 보이고 PC의 전체 경로는 싣지 않는다.
- 자동 배정(`pick_auto`)은 그 대상(sandbox·youtube)에서 **가장 오래 안 쓴 프로필**을 고른다.
  한 번도 안 쓴 프로필이 먼저(설정 순서대로), 다음은 마지막으로 쓴 시각이 가장 이른 것.
  "썼다"는 그 프로필로 예약한 적이 있다는 뜻이다(`posts.updated_at`, 실패도 포함). 시각이 같으면
  나중에 넣은 예약(id가 큰 것)을 더 최근으로 본다.
- R3: 실제 게시의 자동 배정은 최근 확인에서 로그인 안 됨으로 나온 프로필을 뒤로 미룬다
  (`avoid`). 모두 그렇다면 그중에서 고르고, 작업 서비스가 「로그인하기」를 안내한다.
- 2026-11-17(PDF 대조): 실제 게시의 자동 배정은 **로그인이 확인된 프로필 중에서만** 돌아가며
  고른다(`choose_auto`, `profile_logins.state = 'signed_in'`). 확인된 프로필이 하나도 없으면
  예전처럼 고르되(로그인 안 됨으로 나온 것은 뒤로) 왜 실패할 수 있는지 `note`로 알린다.
  연습 모드는 로그인이 필요 없어 예전 그대로다. 「한 영상에는 계정 하나」(posts의 UNIQUE)는 그대로.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app import db
from app.errors import AppError, ErrorKind
from app.ops.rules import check_target


@dataclass(frozen=True)
class Profile:
    name: str  # 화면 이름(유튜브1)
    folder: str  # 폴더 이름(profile-1)
    index: int  # 1부터


@dataclass(frozen=True)
class AutoPick:
    """자동 배정이 이번에 고를 프로필과 그렇게 고른 까닭."""

    profile: Profile
    # True = 로그인이 확인된 프로필 중에서 골랐다, False = 확인된 프로필이 없어 그냥 골랐다,
    # None = 연습 모드라 로그인이 필요 없다
    confirmed: bool | None
    note: str = ""  # 확인된 프로필이 없을 때 미리 알리는 말(쉬운 한국어)


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

    def pick_auto(
        self,
        target: str,
        *,
        avoid: Collection[str] = (),
        only: Collection[str] | None = None,
    ) -> Profile:
        """가장 오래 안 쓴 프로필. 셋을 차례로 돈다(유튜브1 → 2 → 3 → 1 …).

        `only`를 주면 그 안에서만 돈다(하나라도 설정에 있을 때). `avoid`에 든 프로필은 다른 프로필이
        하나라도 있으면 고르지 않는다.
        """
        if not self._profiles:
            raise AppError(ErrorKind.PROFILE_UNKNOWN, detail="profiles가 비어 있음")
        base = list(self._profiles)
        if only is not None:
            base = [p for p in base if p.name in only] or base
        pool = [p for p in base if p.name not in avoid] or base
        used = self._usage(target)
        never = [p for p in pool if p.name not in used]
        if never:
            return never[0]
        return min(pool, key=lambda p: (*used[p.name], p.index))

    def login_sets(
        self, *, now: datetime, trust: timedelta
    ) -> tuple[set[str], set[str]]:
        """(로그인이 확인된 프로필, `trust` 안에 로그인 안 됨으로 나온 프로필) 이름들."""
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT profile, state, checked_at FROM profile_logins"
            ).fetchall()
        names = set(self.names())
        signed_in: set[str] = set()
        signed_out: set[str] = set()
        cutoff = now - trust
        for row in rows:
            name = row["profile"]
            if name not in names:
                continue
            if row["state"] == "signed_in":
                signed_in.add(name)
            elif row["state"] == "signed_out":
                at = _parse_time(row["checked_at"])
                if at is not None and at >= cutoff:
                    signed_out.add(name)
        return signed_in, signed_out

    def choose_auto(
        self, target: str, *, login: bool, now: datetime, trust: timedelta
    ) -> AutoPick:
        """「자동 배정」이 이번에 쓸 프로필. `login`(실제 게시)이면 로그인이 확인된 것 중에서만."""
        if not login:
            return AutoPick(self.pick_auto(target), None)
        signed_in, signed_out = self.login_sets(now=now, trust=trust)
        if signed_in:
            return AutoPick(self.pick_auto(target, only=signed_in), True)
        chosen = self.pick_auto(target, avoid=signed_out)
        if chosen.name in signed_out:
            note = (
                "로그인된 프로필이 없습니다. 프로필 화면에서 [로그인하기]를 눌러 주세요."
            )
        else:
            note = (
                f"로그인을 확인한 프로필이 없어 {with_ro(chosen.name)} 해 봅니다. "
                "로그인돼 있지 않으면 실패하니 프로필 화면에서 [로그인 확인]을 먼저 눌러 주세요."
            )
        return AutoPick(chosen, False, note)

    def resolve(self, name: str | None, target: str, *, avoid: Collection[str] = ()) -> Profile:
        """화면에서 고른 이름. 비었거나 「자동 배정」이면 `pick_auto`."""
        if not name or name == "auto":
            return self.pick_auto(target, avoid=avoid)
        return self.get(name)


def _parse_time(value: str | None) -> datetime | None:
    try:
        at = datetime.fromisoformat(value or "")
    except (TypeError, ValueError):
        return None
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at


def with_ro(name: str) -> str:
    """이름 뒤 「로/으로」(받침 없음·ㄹ 받침이면 「로」). 숫자는 읽는 소리로(1·7·8은 ㄹ)."""
    last = name[-1:] if name else ""
    if not last:
        return name
    if last.isdigit():
        ro = last in "1245789"  # 일·이·사·오·칠·팔·구 → 로, 영·삼·육 → 으로
    elif "가" <= last <= "힣":
        jong = (ord(last) - 0xAC00) % 28
        ro = jong in (0, 8)  # 받침 없음 또는 ㄹ
    else:
        ro = True
    return f"{name}{'로' if ro else '으로'}"
