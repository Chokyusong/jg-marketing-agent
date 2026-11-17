// 운영 규칙과 기록(7단계, R1): 기록 화면의 오늘 숫자 4개, ③칸 설정(프로필 · 연습 모드 · 하루 상한),
// ③칸 아래 최근 게시 기록(4줄), 아래 줄 「오늘 게시 n/상한」.
// - 숫자·기록은 GET /api/stats/today · /api/records. 분석·초안·승인·게시가 끝나면 refreshOps()를 부르고,
//   그 밖에는 30초마다 다시 본다(한국 자정이 지나면 오늘 수가 0으로 돌아온다).
// - 연습 모드 켬 = 연습 페이지(sandbox), 끔 = 실제 게시(youtube, 기본). 처음 값은 기본 게시 방식(browser.default_target).
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
    // 숫자는 실제 게시 기준으로 보이고 연습은 따로(「연습 n」). 시작 전 확인(오늘 상한)은 고른 대상의 것
    const [realStats, practiceStats, records] = await Promise.all([
      api.todayStats('youtube', ops.dailyLimit),
      api.todayStats('sandbox', ops.dailyLimit),
      api.records(RECENT_FETCH),
    ]);
    if (mine !== seq) return; // 그새 대상·상한을 바꿔 다시 불렀다
    const key = JSON.stringify([realStats, practiceStats, records, ops.target]);
    if (key === lastKey && !currentOps().error) return; // 달라진 것이 없으면 다시 그리지 않는다
    lastKey = key;
    const stats = ops.target === 'sandbox' ? practiceStats : realStats;
    setOps({ stats, realStats, practiceStats, records: records.items, total: records.total, error: null });
  } catch (error) {
    if (mine !== seq) return;
    lastKey = null;
    setOps({ error });
  }
}

// R2: 설정 화면에서 하루 상한을 바꿔 저장하면 ③칸 고르기(그 값과 그보다 낮은 값)와 오늘 숫자를 새로
export function limitOptions(max) {
  return [...new Set([max, 5, 3, 1])].filter((n) => n > 0 && n <= max).sort((a, b) => b - a);
}

export function applyDailyMax(max) {
  const box = settingsBox();
  if (!box || box.dataset.limit === String(max)) return;
  box.dataset.limit = String(max);
  const limit = $('limit');
  limit.replaceChildren(...limitOptions(max).map((n) => {
    const option = el('option', { value: String(n), text: `${n}개까지` });
    option.defaultSelected = n === max;
    return option;
  }));
  limit.value = String(max);
  setOps({ dailyLimit: max });
  refreshOps();
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

// 연습 게시 수(오늘): 실제 숫자와 따로, 흐리게
export function practiceCount(ops) {
  const p = ops && ops.practiceStats;
  return p ? p.videos : 0;
}

function renderStats(ops) {
  const s = ops.realStats || null;
  const videos = $('stat-videos');
  const limit = s ? s.daily_limit : ops.dailyLimit;
  videos.replaceChildren(s ? String(s.videos) : '–', el('span', { class: 'slash', text: '/' }), String(limit));
  $('stat-drafts').textContent = s ? String(s.drafts) : '–';
  $('stat-posted').textContent = s ? String(s.posted) : '–';
  const rate = s ? successText(s.success_rate) : null;
  $('stat-success').replaceChildren(...(rate === null ? ['–'] : [rate, el('small', { text: '%' })]));
  const note = $('today-note');
  const practice = practiceCount(ops);
  const practiceMark = practice ? el('span', { class: 'practice-count', text: ` · 연습 ${practice}`, title: '연습 페이지에 단 댓글(실제 게시 숫자에 넣지 않습니다)' }) : '';
  if (ops.error) note.textContent = '오늘 숫자를 불러오지 못했습니다';
  else if (s) note.replaceChildren(`오늘 ${s.day.slice(5).replace('-', '.')} · 실제 게시 기준`, practiceMark);
  // 아래 줄 오늘 게시 n/상한(실제 게시) · 연습 n(흐리게)
  $('today-count').replaceChildren(
    s ? String(s.videos) : '–',
    el('span', { class: 'slash', text: '/' }),
    String(limit),
    s && s.remaining === 0 ? ' · 오늘 상한' : '',
    practice ? el('span', { class: 'practice-count', text: ` · 연습 ${practice}` }) : '',
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

// 게시 줄의 「실제」/「연습」 표(그 밖의 줄은 없음)
export function kindLabel(r) {
  if (r.action !== 'post') return '';
  return r.target === 'sandbox' ? '연습' : r.target === 'youtube' ? '실제' : '';
}

export function kindBadge(r) {
  const label = kindLabel(r);
  if (!label) return null;
  return el('span', {
    class: `kind ${label === '연습' ? 'is-practice' : 'is-real'}`,
    text: label,
    title: label === '연습' ? '연습 페이지에 단 댓글(실제 유튜브가 아님)' : '실제 유튜브에 단 댓글',
  });
}

export function rowClass(r) {
  return r.action === 'post' && r.target === 'sandbox' ? 'is-practice-row' : '';
}

function recordRow(r) {
  const tone = toneOf(r);
  const status = el('td', { class: `st ${tone}`, title: r.reason || null }, [el('b', { text: r.status_label === '게시 완료' ? '성공' : r.status_label === '게시 실패' ? '실패' : r.status_label })]);
  // 댓글이 잘리면 눌러서 기록 화면에서 전문을 본다
  const comment = el('td', { class: 'clip', text: r.comment_text || '–', title: r.comment_text ? `${r.comment_text}${r.disclosed === false ? ' (광고 표기 없음)' : ''}` : null });
  if (r.comment_text) {
    comment.classList.add('is-link');
    comment.tabIndex = 0;
    comment.setAttribute('role', 'link');
    comment.setAttribute('aria-label', `댓글 전문 보기: ${r.comment_text}`);
  }
  return el('tr', { class: rowClass(r) || null }, [
    el('td', { class: 'nowrap', text: formatKst(r.at), title: r.at }),
    el('td', { class: 'clip', text: r.video_title || r.video_id || '–', title: r.video_title || null }),
    el('td', { class: 'nowrap', title: whereText(r) || null }, [kindBadge(r), r.profile || '–']),
    comment,
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
      realStats: null,
      practiceStats: null,
      records: null,
      total: 0,
      error: null,
    },
  });
  setupSettings();
  // ③ 최근 기록의 댓글을 누르면 기록 화면(전문)으로
  const openAll = (event) => {
    const cell = event.target.closest('td.is-link');
    if (!cell) return;
    if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    document.getElementById('records-all').click();
  };
  $('records-body').addEventListener('click', openAll);
  $('records-body').addEventListener('keydown', openAll);
  subscribe(render);
  refreshOps();
  setInterval(refreshOps, REFRESH_MS);
}
