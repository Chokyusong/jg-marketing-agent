// 프로필 화면(R2, UI_SPEC 5절). 카드 세 장: 이름 · 로그인 상태와 채널 이름 · 마지막으로 쓴 때,
// [로그인하기] · [로그인 확인] · [유튜브 열기].
// - [로그인하기]: 그 프로필 폴더로 보통 크롬 창을 구글 로그인 주소로 연다(POST /api/profiles/{name}/login).
//   로그인은 사람이 그 창에서 직접 한다. 프로그램은 아이디·비밀번호를 받거나 치지 않는다.
// - [로그인 확인]: 창 없이 유튜브를 열어 로그인 표시와 채널 이름만 읽는다(POST …/check). 누르거나 치지 않는다.
// - 로그인 창을 닫으면 서버가 한 번 저절로 확인한다. 창이 열려 있거나 확인이 도는 동안 2초마다 다시 본다.
//   서버가 알려 주는 `login_checking`이면 그 카드에 「로그인 확인 중…」을 보이고 단추를 흐리게 한다
//   (창을 닫아 저절로 시작한 확인이면 「창이 닫혀 로그인을 확인하는 중입니다」). 끝나면 결과를 다시 읽는다.
// - 로그인 상태는 아래 줄 「프로필」과 ③칸 프로필 고르기에도 보인다(topbar.js · 이 파일의 paintPicker).
// - 바깥 글(채널 이름)은 textContent로만 넣는다.
import { api } from './api.js';
import { el, targetName } from './format.js';
import { formatKst } from './ops.js';
import { getState, subscribe } from './state.js';
import { refreshStatus, showScreen } from './topbar.js';

const $ = (id) => document.getElementById(id);
const POLL_MS = 2000;
export const AFTER_LOGIN = '로그인을 마치고 크롬 창을 닫은 다음 [로그인 확인]을 누르세요';
export const AUTO_CHECKING = '창이 닫혀 로그인을 확인하는 중입니다';

let items = null; // GET /api/profiles?target=youtube 의 items(로그인 상태 포함)
let lastUsed = {}; // 이름 → { sandbox, youtube }
let busy = null; // 지금 요청을 보내는 프로필 이름
let pollTimer = null;
let pendingFocus = null;

export function loginText(p) {
  if (p.login_checking) return { tone: 'is-wait', text: '로그인 확인 중…' };
  if (p.signed_in === true) return { tone: 'is-ok', text: p.channel_name ? `로그인됨 · ${p.channel_name}` : '로그인됨' };
  if (p.signed_in === false) return { tone: 'is-bad', text: '로그인 안 됨' };
  if (p.checked_at) return { tone: 'is-wait', text: '확인하지 못함' };
  return { tone: 'is-off', text: '아직 확인하지 않았습니다' };
}

function setMessage(text, tone = '') {
  const node = $('profiles-msg');
  node.hidden = !text;
  node.textContent = text;
  node.className = `notice${tone ? ` ${tone}` : ''}`;
}

function errorText(error) {
  return `${error.message || ''} ${error.action || ''}`.trim();
}

function profileCard(p, index) {
  const used = lastUsed[p.name] || {};
  const times = ['youtube', 'sandbox'].filter((t) => used[t]).map((t) => `${formatKst(used[t])} (${targetName(t)})`);
  const login = loginText(p);
  const n = index + 1;
  const mine = busy === p.name;
  const open = p.login_window_open;
  const serverChecking = Boolean(p.login_checking);
  const loginBtn = el('button', {
    type: 'button', class: `btn btn-small${index === 0 && p.signed_in !== true && !open ? ' is-primary' : ''}`,
    id: `profile-${n}-login`, 'data-act': 'login', 'data-profile': p.name, disabled: mine || open || serverChecking, text: '로그인하기',
  });
  const checkBtn = el('button', {
    type: 'button', class: 'btn btn-small', id: `profile-${n}-check`, 'data-act': 'check', 'data-profile': p.name,
    disabled: mine || open || serverChecking, text: (mine && checking) || serverChecking ? '확인 중…' : '로그인 확인',
  });
  const openBtn = el('button', {
    type: 'button', class: 'btn btn-small', id: `profile-${n}-open`, 'data-act': 'open', 'data-profile': p.name,
    disabled: mine || open || serverChecking, text: '유튜브 열기',
  });
  return el('section', { class: 'card', 'aria-label': p.name, 'data-profile': p.name }, [
    el('h3', {}, [p.name, index === 0 ? el('span', { class: 'tag', text: '꼭 필요' }) : null]),
    el('p', { class: 'card-line login-line' }, [
      el('i', { class: `dot ${login.tone}`, 'aria-hidden': 'true' }),
      el('span', { class: 'login-state', text: login.text }),
    ]),
    el('p', { class: 'card-line caption', text: p.checked_at ? `확인한 때 · ${formatKst(p.checked_at)}${p.login_note ? ` · ${p.login_note}` : ''}` : '[로그인 확인]을 누르면 로그인했는지 봅니다' }),
    el('p', { class: 'card-line' }, [
      el('i', { class: `dot ${p.exists ? 'is-ok' : 'is-wait'}`, 'aria-hidden': 'true' }),
      p.exists ? '이 프로필 전용 크롬 폴더가 있습니다' : '크롬 폴더 아직 없음 · 처음 열 때 만듭니다',
    ]),
    el('p', { class: 'card-line', text: `마지막으로 쓴 때 · ${times.length ? times.join(', ') : '없음'}` }),
    open ? el('p', { class: 'notice is-info', text: `${AFTER_LOGIN}. 창을 닫으면 한 번 저절로 확인합니다.` }) : null,
    !open && p.login_checking_auto ? el('p', { class: 'notice is-info', id: `profile-${n}-auto`, text: `${AUTO_CHECKING}(20초쯤 걸릴 수 있습니다)` }) : null,
    el('div', { class: 'card-actions' }, [loginBtn, checkBtn, openBtn]),
  ]);
}

let checking = false;

function render() {
  const body = $('profiles-body');
  const b = getState().browser;
  if (!items) {
    if (!b) {
      body.replaceChildren(el('p', { class: 'empty', text: '프로필을 불러오는 중…' }));
      return;
    }
    items = b.profiles.map((p) => ({ ...p, login_state: null, login_note: '' }));
  }
  const notes = [];
  if (b && !b.chrome_found) notes.push(el('p', { class: 'alert-msg', text: '이 PC에서 크롬을 찾지 못했습니다. 크롬을 설치해 주세요.' }));
  body.replaceChildren(...notes, ...items.map(profileCard));
  applyFocus();
}

function applyFocus() {
  if (!pendingFocus) return;
  const card = [...document.querySelectorAll('#profiles-body .card')].find((c) => c.dataset.profile === pendingFocus);
  if (!card) return;
  pendingFocus = null;
  const button = card.querySelector('[data-act="login"]');
  card.scrollIntoView({ block: 'nearest' });
  (button && !button.disabled ? button : card.querySelector('h3')).focus({ preventScroll: true });
}

// 시작 준비 상자에서: 프로필 화면을 열고 그 프로필의 [로그인하기]로
export function focusProfile(name) {
  pendingFocus = name;
  showScreen('profiles');
}

async function load() {
  try {
    const [youtube, sandbox] = await Promise.all([api.profiles('youtube'), api.profiles('sandbox')]);
    const wasOpen = (items || []).some((p) => p.login_window_open || p.login_checking);
    items = youtube.items;
    lastUsed = {};
    for (const [target, list] of [['sandbox', sandbox], ['youtube', youtube]]) {
      for (const p of list.items) {
        if (!lastUsed[p.name]) lastUsed[p.name] = {};
        if (p.last_used_at) lastUsed[p.name][target] = p.last_used_at;
      }
    }
    const nowOpen = items.some((p) => p.login_window_open || p.login_checking);
    if (wasOpen && !nowOpen) refreshStatus(); // 창을 닫아 저절로 확인했다 → 아래 줄·시작 준비도
  } catch {
    // 못 받아도 아래 줄 상태로 카드는 보인다
  }
  render();
  schedulePoll();
}

function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer = null;
  if (items && items.some((p) => p.login_window_open || p.login_checking)) pollTimer = setTimeout(load, POLL_MS);
}

async function act(name, what) {
  if (busy) return;
  busy = name;
  checking = what === 'check';
  render();
  if (checking) setMessage(`${name} 로그인 확인 중… 창 없이 유튜브를 열어 봅니다(20초쯤 걸릴 수 있습니다)`, '');
  try {
    const call = what === 'login' ? api.profileLogin : what === 'check' ? api.profileCheck : api.profileOpen;
    const res = await call(name);
    const tone = what === 'check' ? (res.signed_in === true ? 'is-ok' : res.signed_in === false ? 'is-bad' : '') : 'is-info';
    setMessage(`${name} · ${res.message}`, tone);
    if (what === 'check') refreshStatus();
  } catch (error) {
    setMessage(`${name} · ${errorText(error)}`, 'is-bad');
  } finally {
    busy = null;
    checking = false;
    await load();
  }
}

// ③칸 프로필 고르기: 이름 옆에 로그인 상태
export function pickerLabel(p) {
  if (!p) return '';
  if (p.signed_in === true) return `${p.name} · 로그인됨`;
  if (p.signed_in === false) return `${p.name} · 로그인 안 됨`;
  return p.name;
}

let lastPicker = '';
function paintPicker(state) {
  const b = state.browser;
  if (!b) return;
  const key = JSON.stringify(b.profiles.map((p) => [p.name, p.signed_in]));
  if (key === lastPicker) return;
  lastPicker = key;
  const byName = Object.fromEntries(b.profiles.map((p) => [p.name, p]));
  for (const option of $('profile').options) {
    if (option.value && byName[option.value]) option.textContent = pickerLabel(byName[option.value]);
  }
}

export function initProfiles() {
  $('profiles-body').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-act]');
    if (!button || button.disabled) return;
    act(button.dataset.profile, button.dataset.act);
  });
  document.addEventListener('screen:show', (event) => {
    if (event.detail === 'profiles') {
      setMessage('');
      render();
      load();
    }
  });
  let lastBrowser = null;
  subscribe((state) => {
    paintPicker(state);
    if (state.screen !== 'profiles' || state.browser === lastBrowser) return;
    lastBrowser = state.browser;
    if (!busy) load();
  });
}
