"""실제 유튜브 영상 페이지에서 게시에 쓰는 화면 요소가 잡히는지 **읽기만** 해서 표로 알려 준다(R3).

    .\\.venv\\Scripts\\python.exe scripts\\check_youtube_page.py <영상 주소 또는 ID>
    .\\.venv\\Scripts\\python.exe scripts\\check_youtube_page.py <영상> --profile 유튜브1
    .\\.venv\\Scripts\\python.exe scripts\\check_youtube_page.py <영상 주소 또는 ID> --show

- 아무것도 입력하거나 누르지 않는다. 댓글 영역을 불러오려고 아래로 내리기만 한다.
  글 입력 칸과 「댓글」 게시 단추는 「댓글 추가...」를 눌러야 생기므로 "눌러야 보임 — 실제 게시 때
  확인"으로 나온다.
- `--profile`을 주지 않으면 **로그인하지 않은 임시 프로필**로 연다(끝나면 지운다). 주면 그 프로필
  폴더(%LOCALAPPDATA%\\JGMarketingAgent\\profiles\\profile-N)를 쓴다. 그 프로필의 크롬 창이 열려
  있으면 닫아 달라고 하고 멈춘다.
- 기본은 창 없이(headless). `--show`를 주면 창을 띄운다(위치는 설정 화면의 「크롬 창을 띄울
  화면」. 그 위치가 모니터 밖이면 주 모니터 안쪽으로 옮긴다). 화면은 한국어(ko-KR)로 연다.
- `--shot 파일.png`: 다 본 뒤의 화면을 그림으로 남긴다(로그인한 프로필이면 계정 정보가 찍힐 수
  있으니 남과 나누지 않는다).
- 화면 요소 이름은 `app/browser/youtube_driver.py`의 `SELECTORS` 한곳에 있다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.browser.chrome import ensure_profile_dir, profile_in_use, window_arg  # noqa: E402
from app.browser.screens import check_window_position, read_monitors  # noqa: E402
from app.browser.youtube_check import format_table, inspect_page  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.ops.profiles import ProfileService  # noqa: E402
from app.youtube.url_parser import parse_video_id, watch_url  # noqa: E402


def _position(settings) -> tuple[int, int]:
    wanted = settings.browser.window_position
    try:
        monitors = read_monitors()
    except Exception:
        monitors = []
    return check_window_position(wanted, monitors).position or wanted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="유튜브 영상 페이지 화면 요소 점검(읽기만)")
    parser.add_argument("video", help="영상 주소 또는 11자 영상 ID")
    parser.add_argument(
        "--profile", default="", help="프로필 이름(예: 유튜브1). 비우면 임시 프로필"
    )
    parser.add_argument("--show", action="store_true", help="창을 띄운다(기본은 창 없이)")
    parser.add_argument("--timeout", type=int, default=30, help="페이지를 여는 데 기다릴 초")
    parser.add_argument("--shot", default="", help="다 본 뒤 화면을 저장할 PNG 경로")
    args = parser.parse_args(argv)

    try:
        video_id = parse_video_id(args.video)
    except AppError as exc:
        print(f"영상 주소로 읽을 수 없습니다: {exc.message}")
        return 2

    settings = load_settings()
    temp_dir: str | None = None
    if args.profile:
        try:
            profile = ProfileService(settings.profiles, db_path=settings.db_path).get(args.profile)
        except AppError:
            names = ", ".join(settings.profiles)
            print(f"설정에 없는 프로필입니다: {args.profile} (있는 이름: {names})")
            return 2
        user_dir = ensure_profile_dir(settings.browser.profiles_root, profile.folder)
        if profile_in_use(user_dir):
            print(f"{args.profile} 프로필의 크롬 창이 열려 있습니다. 창을 닫고 다시 실행해 주세요.")
            return 3
        who = f"{args.profile} 프로필({profile.folder})"
    else:
        temp_dir = tempfile.mkdtemp(prefix="jg-check-")
        user_dir = Path(temp_dir)
        who = "로그인하지 않은 임시 프로필"

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    launch_args = [window_arg(_position(settings)), "--no-first-run", "--no-default-browser-check"]
    if args.show:
        launch_args.append("--window-size=1280,900")
    url = watch_url(video_id)
    print(f"{who}로 {'창을 띄워' if args.show else '창 없이'} 엽니다: {url}")
    try:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                str(user_dir),
                channel="chrome",
                headless=not args.show,
                args=launch_args,
                no_viewport=args.show,
                viewport=None if args.show else {"width": 1280, "height": 900},
                locale="ko-KR",
                timeout=30_000,
            )
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                except PlaywrightError as exc:
                    first = str(exc).strip().splitlines()[0][:160] if str(exc).strip() else ""
                    print(f"영상 페이지를 열지 못했습니다: {first}")
                    return 4
                check = inspect_page(page, video_id)
                print()
                print(format_table(check))
                if args.shot:
                    shot = Path(args.shot)
                    shot.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(shot))
                    print(f"\n화면을 저장했습니다: {shot}")
            finally:
                ctx.close()
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
