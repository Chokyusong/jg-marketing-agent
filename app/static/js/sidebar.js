// 사이드바: 메뉴 이동(해당 칸 강조), 좁은 화면 접기, 시스템 상태와 할당량 표시.
import { api } from './api.js';
import { setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);

function setupMenu() {
  const sidebar = $('sidebar');
  const toggle = $('menu-toggle');
  const scrim = $('scrim');
  const setOpen = (open) => {
    sidebar.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    scrim.hidden = !open;
  };
  toggle.addEventListener('click', () => setOpen(!sidebar.classList.contains('is-open')));
  scrim.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setOpen(false);
  });

  for (const link of sidebar.querySelectorAll('a.menu-item')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      for (const other of sidebar.querySelectorAll('.menu-item')) {
        other.classList.toggle('is-active', other === link);
        if (other === link) other.setAttribute('aria-current', 'page');
        else other.removeAttribute('aria-current');
      }
      const target = $(link.dataset.target);
      target?.scrollIntoView({ block: 'start' });
      if (target?.classList.contains('panel')) {
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

export function initSidebar() {
  setupMenu();
  subscribe(renderStatus);
  loadStatus();
}
