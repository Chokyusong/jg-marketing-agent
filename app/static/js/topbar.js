// 위 줄: 메뉴 이동(해당 칸 잠깐 강조), 좁은 화면 메뉴 단추, 시스템 상태, 할당량 표시.
import { api } from './api.js';
import { setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);

function setupMenu() {
  const nav = $('nav');
  const toggle = $('menu-toggle');
  const setOpen = (open) => {
    nav.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  };
  toggle.addEventListener('click', () => setOpen(!nav.classList.contains('is-open')));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setOpen(false);
  });

  for (const link of nav.querySelectorAll('a')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      for (const other of nav.querySelectorAll('a')) {
        other.classList.toggle('on', other === link);
        if (other === link) other.setAttribute('aria-current', 'true');
        else other.removeAttribute('aria-current');
      }
      const target = $(link.dataset.target);
      target?.scrollIntoView({ block: 'start' });
      if (target?.classList.contains('column')) {
        target.classList.add('is-focus');
        setTimeout(() => target.classList.remove('is-focus'), 1200);
      }
      setOpen(false);
    });
  }
}

async function loadStatus() {
  try {
    const data = await api.status();
    setState({ youtubeKey: data.youtube.key_configured, quota: data.youtube.quota });
  } catch {
    setState({ youtubeKey: null });
  }
}

function renderStatus(state) {
  const dot = $('status-youtube-dot');
  const text = $('status-youtube');
  dot.classList.remove('is-ok', 'is-bad', 'is-wait');
  if (state.youtubeKey === true) {
    dot.classList.add('is-ok');
    text.textContent = '키 설정됨';
  } else if (state.youtubeKey === false) {
    dot.classList.add('is-bad');
    text.textContent = '키 없음 · .env 확인';
  } else {
    dot.classList.add('is-wait');
    text.textContent = '확인 못 함';
  }
  if (state.quota) {
    $('quota-used').textContent = state.quota.used_today.toLocaleString('ko-KR');
    $('quota-limit').textContent = state.quota.daily_limit.toLocaleString('ko-KR');
  }
}

export function initTopbar() {
  setupMenu();
  subscribe(renderStatus);
  loadStatus();
}
