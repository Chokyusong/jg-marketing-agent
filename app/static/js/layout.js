// 한 화면 배치(R1). CSS 격자가 화면을 왼쪽 줄 · 위 줄 · 화면 내용 · 아래 줄로 나누고 페이지는 스크롤하지 않는다
// (style.css). 칸 제목은 칸 맨 위에 고정되고, 넘치는 내용은 그 칸 몸통(.col-body) 안에서만 스크롤한다.
// ①칸은 영상 목록 한 곳만 스크롤한다. 여기서는 목록이 다시 그려지거나 창 크기가 바뀌어도
// 고른 영상 줄이 목록 안에서 보이게만 맞춘다(페이지는 움직이지 않는다).
import { subscribe } from './state.js';

const FIT = '(min-width: 0px)'; // R1: 모든 크기에서 목록이 자기 자리 안에서만 스크롤한다

// 목록 상자 안에서만 스크롤을 옮긴다(scrollIntoView는 페이지나 칸까지 움직일 수 있어 쓰지 않는다)
function keepInList(list, row) {
  const top = row.offsetTop; // .video-list는 position: relative라 줄 위치가 목록 기준이다
  const bottom = top + row.offsetHeight;
  if (top < list.scrollTop) list.scrollTop = top;
  else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight;
}

export function initLayout() {
  const list = document.getElementById('video-list');
  if (!list) return;
  const fit = window.matchMedia(FIT);
  let lastSelected = null;
  let frame = 0;
  const reveal = (force) => {
    const row = list.querySelector('.vid[aria-pressed="true"]');
    const id = row ? row.dataset.id : null;
    if (row && fit.matches && (force || id !== lastSelected)) keepInList(list, row);
    lastSelected = id;
  };
  subscribe(() => reveal(false));
  const onResize = () => {
    if (!frame) frame = requestAnimationFrame(() => { frame = 0; reveal(true); });
  };
  window.addEventListener('resize', onResize);
  fit.addEventListener('change', onResize);
}
