// 시작 준비 상자(R2, UI_SPEC 7절). 작업 화면 위 한 줄: 유튜브 연결 · AI 모델 · 프로필 로그인.
// - 상태는 GET /api/status(topbar.js가 30초마다 읽는다)에서 온다. 셋 다 되면 상자가 사라진다.
// - 단추를 누르면 그것을 고치는 곳으로 간다: [API 키 넣기]·[모델 확인] → 설정 화면 그 칸, [유튜브1 로그인] → 프로필 화면.
// - [닫기]로 닫을 수 있다(프로그램을 다시 켜면 다시 보인다). 연습 모드는 키·로그인 없이도 된다고 알린다.
// - R4: 지금 모델이 추천 모델(코드 기본값)이 아니고 추천 모델이 이 PC에 있으면
//   「지금 ○○ — 추천 모델 △△로 바꾸기 [바꾸기]」. [바꾸기]는 프로그램 설정에 모델을 저장한다(.env는 그대로).
import { api } from './api.js';
import { focusProfile } from './profiles.js';
import { focusSetting } from './settings.js';
import { getState, subscribe } from './state.js';
import { aiStatusText, refreshStatus, youtubeStatusText } from './topbar.js';

const $ = (id) => document.getElementById(id);
const CLOSED_KEY = 'jg-setup-closed';

let closed = false;
try {
  closed = sessionStorage.getItem(CLOSED_KEY) === '1';
} catch {
  closed = false;
}

export function aiReady(ai) {
  return Boolean(ai && !ai.error && ai.reachable && ai.installed);
}

function sameModel(a, b) {
  const norm = (n) => {
    const t = String(n || '').trim().toLowerCase();
    return t.includes(':') ? t : `${t}:latest`;
  };
  return norm(a) === norm(b);
}

// R4: 추천 모델로 바꾸자는 줄. 바꿀 것이 없으면 null
export function recommendLine(ai) {
  if (!aiReady(ai) || !ai.recommended_installed || !ai.recommended_model) return null;
  if (sameModel(ai.model, ai.recommended_model)) return null;
  return {
    done: false,
    tone: 'is-wait',
    text: `지금 ${ai.model} — 추천 모델 ${ai.recommended_model}로 바꾸기`,
    recommend: ai.recommended_model,
  };
}

function firstProfile(browser) {
  return browser && browser.profiles.length ? browser.profiles[0] : null;
}

// 세 줄 각각 { done, tone, text }
export function setupLines(state) {
  const youtube = youtubeStatusText(state.youtubeKey);
  const ai = aiStatusText(state.ai);
  const p = firstProfile(state.browser);
  let profile;
  if (!state.browser) profile = { done: false, tone: 'is-wait', text: '확인 못 함' };
  else if (!state.browser.chrome_found) profile = { done: false, tone: 'is-bad', text: '크롬 없음 · 크롬을 설치해 주세요' };
  else if (p && p.signed_in === true) profile = { done: true, tone: 'is-ok', text: p.channel_name ? `로그인됨 · ${p.channel_name}` : '로그인됨' };
  else if (p && p.signed_in === false) profile = { done: false, tone: 'is-bad', text: '로그인 안 됨' };
  else profile = { done: false, tone: 'is-wait', text: '아직 확인하지 않았습니다' };
  return {
    youtube: { done: state.youtubeKey === true, tone: youtube.tone, text: youtube.text },
    ai: recommendLine(state.ai) || { done: aiReady(state.ai), tone: ai.tone, text: ai.text },
    profile,
  };
}

function paintLine(name, line) {
  const item = $(`setup-${name}`);
  item.classList.toggle('is-done', line.done);
  const dot = item.querySelector('.dot');
  dot.classList.remove('is-ok', 'is-bad', 'is-wait');
  dot.classList.add(line.tone);
  $(`setup-${name}-state`).textContent = line.text;
  const btn = $(`setup-${name}-btn`);
  btn.hidden = line.done;
  if (name === 'ai') {
    btn.textContent = line.recommend ? '바꾸기' : '모델 확인';
    btn.dataset.recommend = line.recommend || '';
  }
}

async function useRecommended(btn) {
  const model = btn.dataset.recommend;
  btn.disabled = true;
  try {
    await api.saveSettings({ 'llm.model': model }); // 프로그램 설정에만 저장한다
    await refreshStatus();
  } catch {
    focusSetting('set-model'); // 저장하지 못하면 설정 화면의 모델 칸으로
  } finally {
    btn.disabled = false;
  }
}

function render(state) {
  const box = $('setup-box');
  const known = state.youtubeKey !== null || state.browser !== null;
  const lines = setupLines(state);
  const all = lines.youtube.done && lines.ai.done && lines.profile.done;
  const show = known && !all && !closed;
  if (show) for (const [name, line] of Object.entries(lines)) paintLine(name, line);
  if (box.hidden === show) box.hidden = !show;
  $('screen-work').classList.toggle('has-setup', show);
}

export function initSetup() {
  $('setup-youtube-btn').addEventListener('click', () => focusSetting('set-key'));
  $('setup-ai-btn').addEventListener('click', () => {
    const btn = $('setup-ai-btn');
    if (btn.dataset.recommend) useRecommended(btn);
    else focusSetting('set-model');
  });
  $('setup-profile-btn').addEventListener('click', () => focusProfile($('setup-profile-btn').dataset.profile));
  $('setup-close').addEventListener('click', () => {
    closed = true;
    try {
      sessionStorage.setItem(CLOSED_KEY, '1');
    } catch {
      // 저장하지 못해도 이번에는 닫힌다
    }
    render(getState());
  });
  subscribe(render);
}
