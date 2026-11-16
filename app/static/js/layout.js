// 3열이 창 아래로 잘리지 않게(9단계). 넓은 화면(3열, 1121px 이상)에서 세 칸의 최대 높이를
// "창 높이 − 3열이 시작하는 위치"로 둔다. 내용이 그보다 길면 그 칸 안에서만 세로로 스크롤한다.
// 1920×1080에서는 내용이 다 들어가 스크롤이 생기지 않는다. 프로그램 창 기본 크기(1600×1000)처럼
// 낮은 창에서만 칸 안 스크롤이 생긴다. 좁은 화면(2열·1열)은 페이지가 그대로 길어진다.
const WIDE = '(min-width: 1121px)';
const MIN_CAP = 420; // 이보다 낮게 남으면 자르지 않는다(너무 낮은 창에서는 페이지 스크롤이 낫다)

export function initLayout() {
  const workspace = document.querySelector('.workspace');
  if (!workspace) return;
  const wide = window.matchMedia(WIDE);
  let frame = 0;
  const fit = () => {
    frame = 0;
    if (!wide.matches) {
      workspace.classList.remove('is-capped');
      workspace.style.removeProperty('--col-max');
      return;
    }
    const top = workspace.getBoundingClientRect().top + window.scrollY;
    const room = Math.floor(window.innerHeight - top - 2);
    if (room < MIN_CAP) {
      workspace.classList.remove('is-capped');
      workspace.style.removeProperty('--col-max');
      return;
    }
    workspace.style.setProperty('--col-max', `${room}px`);
    workspace.classList.add('is-capped');
  };
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(fit);
  };
  window.addEventListener('resize', schedule);
  wide.addEventListener('change', schedule);
  // 위 줄·제목 영역 높이가 바뀌면(글꼴을 늦게 불러올 때 등) 다시 잰다
  const watch = new ResizeObserver(schedule);
  for (const sel of ['.top', '.hero', '.progress']) {
    const node = document.querySelector(sel);
    if (node) watch.observe(node);
  }
  fit();
}
