// 운영 규칙과 기록(7단계, R1): 기록 화면의 오늘 숫자 4개, ③칸 설정(프로필 · 연습 모드 · 하루 상한),
// ③칸 아래 최근 게시 기록(4줄), 아래 줄 「오늘 게시 n/상한」.
// - 숫자·기록은 GET /api/stats/today · /api/records. 분석·초안·승인·게시가 끝나면 refreshOps()를 부르고,
//   그 밖에는 30초마다 다시 본다(한국 자정이 지나면 오늘 수가 0으로 돌아온다).
// - 연습 모드 켬 = 연습 페이지(sandbox), 끔 = 실제 유튜브(youtube). 처음 값은 기본 작업 대상(browser.default_target).
//   고른 값은 화면 상태에만 둔다. 게시 작업이 이 값으로 예약하고, 서버가 상한을 다시 강제한다.
// - 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { el, targetName } from './format.js';
import { getState, setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const REFRESH_MS = 30000;
const RECENT_ROWS = 4; // ③칸 아래 최근 게시 기록 줄 수
const RECENT_FETCH = 60; // 게시 기록만 고르려고 넉넉히 받는다(분석·초안 기록이 섞여 있다)

let lastKey = null;
let seq = 0;

const settingsBox = () => document.querySelector('.exec-settings');

// 한국 시각으로 「11.16 14:32」
export function formatKst(iso) {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return '';
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(t).map((p) => [p.type, p.value]),
  );
  return `${parts.month}.${parts.day} ${parts.hour}:${parts.minute}`;
}

// 성공률: 오늘 게시 시도가 없으면 null → 「–」
export function successText(rate) {
  if (rate === null || rate === undefined) return null;
  return String(Math.round(rate * 100));
}

function currentOps() {
  return getState().ops;
}

function setOps(patch) {
  setState({ ops: { ...currentOps(), ...patch } });
}

export async function refreshOps() {
  const ops = currentOps();
  if (!ops) return;
  const mine = ++seq;
  try {
    const [stats, records] = await Promise.all([
      api.todayStats(ops.target, ops.dailyLimit),
      api.records(RECENT_FETCH),
    ]);
    if (mine !== seq) return; // 그새 대상·상한을 바꿔 다시 불렀다
    const key = JSON.stringify([stats, records]);
    if (key === lastKey && !currentOps().error) return; // 달라진 것이 없으면 다시 그리지 않는다
    lastKey = key;
    setOps({ stats, records: records.items, total: records.total, error: null });
  } catch (error) {
    if (mine !== seq) return;
    lastKey = null;
    setOps({ error });
  }
}

export function practiceText(on) {
  return on ? '켜짐 · 연습 페이지에 답니다' : '꺼짐 · 실제 유튜브에 답니다';
}

function setupSettings() {
  const profile = $('profile');
  const limit = $('limit');
  const practice = $('practice-mode');
  profile.addEventListener('change', () => setOps({ profile: profile.value }));
  limit.addEventListener('change', () => {
    setOps({ dailyLimit: Number(limit.value) });
    refreshOps();
  });
  practice.addEventListener('change', () => {
    $('practice-text').textContent = practiceText(practice.checked);
    setOps({ target: practice.checked ? 'sandbox' : 'youtube' });
    refreshOps();
  });
}

function renderStats(ops) {
  const s = ops.stats;
  const videos = $('stat-videos');
  const limit = s ? s.daily_limit : ops.dailyLimit;
  videos.replaceChildren(s ? String(s.videos) : '–', el('span', { class: 'slash', text: '/' }), String(limit));
  $('stat-drafts').textContent = s ? String(s.drafts) : '–';
  $('stat-posted').textContent = s ? String(s.posted) : '–';
  const rate = s ? successText(s.success_rate) : null;
  $('stat-success').replaceChildren(...(rate === null ? ['–'] : [rate, el('small', { text: '%' })]));
  const note = $('today-note');
  if (ops.error) note.textContent = '오늘 숫자를 불러오지 못했습니다';
  else if (s) note.textContent = `오늘 ${s.day.slice(5).replace('-', '.')} · ${targetName(s.target)} 기준`;
  // 아래 줄 오늘 게시 n/상한
  $('today-count').replaceChildren(
    s ? String(s.videos) : '–',
    el('span', { class: 'slash', text: '/' }),
    String(limit),
    s && s.remaining === 0 ? ' · 오늘 상한' : '',
  );
}

// 결과 칸: 게시면 「게시 완료/게시 실패」, 그 밖은 「초안 생성 · 완료」처럼 무엇을 했는지 함께
export function resultText(r) {
  return r.action === 'post' ? r.status_label : `${r.action_label} · ${r.status_label}`;
}

export function toneOf(r) {
  return r.result === 'success' ? 'is-ok' : r.result === 'failure' ? 'is-bad' : 'is-info';
}

export function whereText(r) {
  return [r.profile, targetName(r.target)].filter(Boolean).join(' · ');
}

function recordRow(r) {
  const tone = toneOf(r);
  const status = el('td', { class: `st ${tone}`, title: r.reason || null }, [el('b', { text: r.status_label === '게시 완료' ? '성공' : r.status_label === '게시 실패' ? '실패' : r.status_label })]);
  return el('tr', {}, [
    el('td', { class: 'nowrap', text: formatKst(r.at), title: r.at }),
    el('td', { class: 'clip', text: r.video_title || r.video_id || '–', title: r.video_title || null }),
    el('td', { class: 'nowrap', text: r.profile || '–', title: whereText(r) || null }),
    el('td', { class: 'clip', text: r.comment_text || '–', title: r.comment_text || null }),
    status,
  ]);
}

function emptyRow(text) {
  return el('tr', {}, [el('td', { colspan: '5', class: 'empty-row', text })]);
}

function renderRecords(ops) {
  const body = $('records-body');
  const meta = $('records-meta');
  if (ops.error && !ops.records) {
    body.replaceChildren(emptyRow(`기록을 불러오지 못했습니다. ${ops.error.message || ''}`));
    return;
  }
  if (!ops.records) return;
  const posts = ops.records.filter((r) => r.action === 'post').slice(0, RECENT_ROWS);
  meta.textContent = posts.length ? `최근 게시 ${posts.length}줄` : '';
  if (!posts.length) {
    body.replaceChildren(emptyRow('아직 게시 기록이 없습니다. [댓글 달기]를 누르면 여기에 남습니다.'));
    return;
  }
  body.replaceChildren(...posts.map(recordRow));
}

let lastOps = null;
function render(state) {
  const ops = state.ops;
  if (!ops || ops === lastOps) return; // 다른 칸의 상태가 바뀔 때는 다시 그리지 않는다
  lastOps = ops;
  renderStats(ops);
  renderRecords(ops);
}

export function initOps() {
  const box = settingsBox();
  const practice = $('practice-mode');
  // 새로 고쳐도 브라우저가 앞서 바꾼 스위치를 되살리지 않게 처음 값(기본 작업 대상)으로
  practice.checked = practice.defaultChecked;
  $('practice-text').textContent = practiceText(practice.checked);
  setState({
    ops: {
      target: practice.checked ? 'sandbox' : 'youtube',
      profile: $('profile').value,
      dailyLimit: Number($('limit').value || box.dataset.limit || 10),
      stats: null,
      records: null,
      total: 0,
      error: null,
    },
  });
  setupSettings();
  subscribe(render);
  refreshOps();
  setInterval(refreshOps, REFRESH_MS);
}
