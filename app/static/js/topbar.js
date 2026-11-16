// 위 줄: 메뉴 이동(해당 칸 잠깐 강조), 좁은 화면 메뉴 단추, 시스템 상태(AI·YOUTUBE·BROWSER), 할당량 표시.
import { api } from './api.js';
import { setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const STATUS_REFRESH_MS = 30000;

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

// 다시 볼 때 달라진 것이 없으면 화면 전체를 다시 그리지 않는다(목록·글 상자가 흔들리지 않게)
let lastStatusKey = null;
function setIfChanged(patch) {
  const key = JSON.stringify(patch);
  if (key === lastStatusKey) return;
  lastStatusKey = key;
  setState(patch);
}

async function loadStatus() {
  try {
    const data = await api.status();
    setIfChanged({
      youtubeKey: data.youtube.key_configured, quota: data.youtube.quota, ai: data.ai || null, browser: data.browser || null,
    });
  } catch {
    setIfChanged({ youtubeKey: null, ai: null, browser: null });
  }
}

export const refreshStatus = loadStatus;

// BROWSER 상태 한 줄(8단계): 크롬·Playwright·프로필 폴더. 게시 작업 중이면 「작업 중」.
export function browserStatusText(browser, job) {
  if (!browser) return { tone: 'is-wait', text: '확인 못 함', title: '' };
  if (!browser.chrome_found) {
    return { tone: 'is-bad', text: '크롬 없음', title: '크롬을 설치하거나 config.yaml의 browser.chrome_path에 chrome.exe 위치를 적어 주세요.' };
  }
  const ready = browser.profiles.filter((p) => p.exists).length;
  const title = browser.playwright_ready
    ? `프로필 폴더 ${ready}/${browser.profiles.length}개 있음. 구글 로그인은 scripts\\setup_profile.ps1로 직접 합니다.`
    : 'Playwright가 없어 테스트 페이지 자동 실행을 못 합니다. pip install -r requirements.txt';
  if (job && !job.finished) return { tone: 'is-wait', text: `크롬 · 작업 중`, title };
  if (!browser.playwright_ready) return { tone: 'is-bad', text: '크롬 · 자동 실행 불가', title };
  return { tone: 'is-ok', text: `크롬 · 프로필 ${ready}/${browser.profiles.length}`, title };
}

function renderBrowser(state) {
  const view = browserStatusText(state.browser, state.job);
  const dot = $('status-browser-dot');
  dot.classList.remove('is-ok', 'is-bad', 'is-wait');
  dot.classList.add(view.tone);
  $('status-browser').textContent = view.text;
  const item = $('status-browser-item');
  if (view.title) item.title = view.title;
  else item.removeAttribute('title');
}

// AI 상태 한 줄: 정상이면 「공급자 · 모델 · 로컬/외부」, 문제면 짧은 이유. 자세한 안내는 마우스를 올리면.
export function aiStatusText(ai) {
  if (!ai) return { tone: 'is-wait', text: '확인 못 함', title: '' };
  const where = ai.local ? '로컬' : '외부';
  const title = ai.error ? `${ai.error.message} ${ai.error.action}`.trim() : '';
  if (ai.error && ai.error.kind === 'llm_provider_unknown') {
    return { tone: 'is-bad', text: `${ai.provider} · 설정 확인`, title };
  }
  if (!ai.reachable) return { tone: 'is-bad', text: `${ai.provider} · 꺼짐`, title };
  if (!ai.installed) return { tone: 'is-bad', text: `${ai.model} · 모델 없음`, title };
  return { tone: 'is-ok', text: `${ai.provider} · ${ai.model} · ${where}`, title: '' };
}

function renderAI(state) {
  const dot = $('status-ai-dot');
  const text = $('status-ai');
  dot.classList.remove('is-ok', 'is-bad', 'is-wait');
  const view = aiStatusText(state.ai);
  dot.classList.add(view.tone);
  text.textContent = view.text;
  const item = $('status-ai-item');
  if (view.title) item.title = view.title;
  else item.removeAttribute('title');
}

function renderStatus(state) {
  renderAI(state);
  renderBrowser(state);
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
  // Ollama를 켜고 끄면 새로 고치지 않아도 위 줄이 따라오게 30초마다 다시 본다(가벼운 요청)
  setInterval(loadStatus, STATUS_REFRESH_MS);
}
