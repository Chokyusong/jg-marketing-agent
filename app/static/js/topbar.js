// 틀(R1): 왼쪽 줄로 화면 바꾸기(작업 · 기록 · 프로필 · 설정), 위 줄 화면 이름, 아래 줄 상태 네 가지.
// - 화면 네 개는 한 페이지 안의 구역이다. 보이기/숨기기만 바꾸므로 작업 화면의 고른 영상·초안·진행 중인
//   게시는 다른 화면에 갔다 와도 그대로 남는다. 화면이 바뀌면 document에 'screen:show'를 알린다(screens.js가 불러온다).
// - 아래 줄 상태를 누르면 관련 화면으로 간다. 준비가 안 된 화면에는 왼쪽 줄에 작은 붉은 점.
// - 좁은 창(1100px 아래)에서는 작업 화면 세 칸을 탭으로 하나씩 보인다(showColumn).
import { api } from './api.js';
import { getState, setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const STATUS_REFRESH_MS = 30000;
const SCREENS = { work: '작업', records: '기록', profiles: '프로필', settings: '설정' };

export function showScreen(name, { focus = false } = {}) {
  if (!SCREENS[name]) return;
  for (const key of Object.keys(SCREENS)) {
    $(`screen-${key}`).hidden = key !== name;
    const btn = $(`nav-${key}`);
    if (key === name) btn.setAttribute('aria-current', 'page');
    else btn.removeAttribute('aria-current');
  }
  $('top').dataset.screen = name;
  $('screen-title').textContent = SCREENS[name];
  if (focus) $('screen-title').focus({ preventScroll: true });
  if (getState().screen !== name) setState({ screen: name });
  document.dispatchEvent(new CustomEvent('screen:show', { detail: name }));
}

// 좁은 창: 세 칸 가운데 하나만(넓은 창에서는 셋 다 보이므로 아무 일도 하지 않는 것과 같다)
export function showColumn(n, { focus = false } = {}) {
  const work = $('screen-work');
  work.dataset.col = String(n);
  for (const tab of work.querySelectorAll('.col-tab')) {
    const on = tab.dataset.col === String(n);
    tab.setAttribute('aria-selected', String(on));
    tab.tabIndex = on ? 0 : -1;
    if (on && focus) tab.focus();
  }
}

function setupNav() {
  for (const btn of document.querySelectorAll('button[data-screen]')) {
    btn.addEventListener('click', () => showScreen(btn.dataset.screen, { focus: true }));
  }
  const tabs = [...document.querySelectorAll('.col-tab')];
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => showColumn(Number(tab.dataset.col)));
    tab.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      event.preventDefault();
      const next = tabs[(i + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
      showColumn(Number(next.dataset.col), { focus: true });
    });
  });
  showScreen('work');
  showColumn(1);
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

// 프로필 상태 한 줄(아래 줄): 크롬, 로그인 확인 결과(R2). 게시 중이면 「게시 중」.
export function browserStatusText(browser, job) {
  if (!browser) return { tone: 'is-wait', text: '확인 못 함', title: '' };
  if (!browser.chrome_found) {
    return { tone: 'is-bad', text: '크롬 없음', title: '이 PC에서 크롬을 찾지 못했습니다. 크롬을 설치해 주세요.' };
  }
  const total = browser.profiles.length;
  const signed = browser.profiles.filter((p) => p.signed_in === true).length;
  const first = browser.profiles[0];
  const title = browser.playwright_ready
    ? `로그인된 프로필 ${signed}개 / ${total}개. 누르면 프로필 화면으로 갑니다.`
    : '자동 입력 도구가 설치되지 않아 연습 모드와 내 채널 영상 자동 게시를 쓸 수 없습니다.';
  if (job && !job.finished) return { tone: 'is-wait', text: '게시 중', title };
  if (!browser.playwright_ready) return { tone: 'is-bad', text: '자동 입력 불가', title };
  if (signed) return { tone: 'is-ok', text: `${signed}/${total} 로그인됨`, title };
  if (first && first.signed_in === false) return { tone: 'is-bad', text: '로그인 안 됨', title };
  return { tone: 'is-wait', text: '로그인 확인 전', title };
}

// AI 상태 한 줄: 정상이면 「모델 · 이 PC/외부」, 문제면 짧은 이유. 자세한 안내는 마우스를 올리면.
export function aiStatusText(ai) {
  if (!ai) return { tone: 'is-wait', text: '확인 못 함', title: '' };
  const where = ai.local ? '이 PC' : '외부';
  const title = ai.error ? `${ai.error.message} ${ai.error.action}`.trim() : '';
  if (ai.error && ai.error.kind === 'llm_provider_unknown') return { tone: 'is-bad', text: '설정 확인 필요', title };
  if (!ai.reachable) return { tone: 'is-bad', text: '꺼져 있음', title };
  if (!ai.installed) return { tone: 'is-bad', text: `${ai.model} · 모델 없음`, title };
  return { tone: 'is-ok', text: `${ai.model} · ${where}`, title: '' };
}

export function youtubeStatusText(key) {
  if (key === true) return { tone: 'is-ok', text: '연결됨', title: 'API 키가 있습니다(값은 보이지 않습니다).' };
  if (key === false) return { tone: 'is-bad', text: '키 없음', title: '유튜브 API 키가 없어 영상을 불러올 수 없습니다. 설정 화면의 「유튜브 연결」에 키를 넣어 주세요.' };
  return { tone: 'is-wait', text: '확인 못 함', title: '' };
}

function paintItem(name, view) {
  const dot = $(`status-${name}-dot`);
  dot.classList.remove('is-ok', 'is-bad', 'is-wait');
  dot.classList.add(view.tone);
  $(`status-${name}`).textContent = view.text;
  const item = $(`status-${name}-item`);
  if (view.title) item.title = view.title;
  else item.removeAttribute('title');
}

function renderStatus(state) {
  const ai = aiStatusText(state.ai);
  const youtube = youtubeStatusText(state.youtubeKey);
  const browser = browserStatusText(state.browser, state.job);
  paintItem('ai', ai);
  paintItem('youtube', youtube);
  paintItem('browser', browser);
  // 준비가 안 된 화면: 프로필(크롬·폴더), 설정(AI·유튜브 키)
  $('nav-profiles-dot').hidden = !(state.browser && browser.tone === 'is-bad');
  $('nav-settings-dot').hidden = !(ai.tone === 'is-bad' || youtube.tone === 'is-bad');
}

export function initTopbar() {
  setupNav();
  subscribe(renderStatus);
  loadStatus();
  // AI 모델을 켜고 끄면 새로 고치지 않아도 아래 줄이 따라오게 30초마다 다시 본다(가벼운 요청)
  setInterval(loadStatus, STATUS_REFRESH_MS);
}
