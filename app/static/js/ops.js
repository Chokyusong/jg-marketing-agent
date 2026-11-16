// 운영 규칙과 기록(7단계): 제목 영역의 오늘 통계 4개, 03칸 설정 4줄, 아래 작업 기록 표.
// - 통계·기록은 GET /api/stats/today · /api/records. 분석·초안·승인이 끝나면 report.js가 refreshOps()를
//   부르고, 그 밖에는 30초마다 다시 본다(한국 자정이 지나면 오늘 수가 0으로 돌아온다).
// - 03칸: 사용 프로필(자동 배정 = 가장 오래 안 쓴 프로필), 작업 방식(대상: youtube = 사람이 게시,
//   sandbox = 테스트 페이지 자동 실행), 일일 제한(설정값 이하로만), 오늘 작업 n / 상한.
//   고른 값은 화면 상태에만 둔다. 게시 실행(8단계)이 이 값으로 예약하고, 서버가 상한을 다시 강제한다.
// - 기록 표는 최근 3줄만(넓은 화면에서 높이를 고정한 띠, 2026-11-17 한 화면 배치)(전체 보기는 9단계 VIEW ALL, panels.js). 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { el } from './format.js';
import { getState, setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const REFRESH_MS = 30000;
const RECENT_ROWS = 3;

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
      api.records(RECENT_ROWS),
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

function setupSettings() {
  const box = settingsBox();
  const profile = $('profile');
  const limit = $('limit');
  profile.addEventListener('change', () => setOps({ profile: profile.value }));
  limit.addEventListener('change', () => {
    setOps({ dailyLimit: Number(limit.value) });
    refreshOps();
  });
  for (const radio of box.querySelectorAll('input[name="mode"]')) {
    radio.addEventListener('change', () => {
      if (!radio.checked) return;
      setOps({ target: radio.value });
      refreshOps();
    });
  }
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
  if (ops.error) note.textContent = '오늘 통계를 불러오지 못했습니다';
  else if (s) note.textContent = `오늘 ${s.day.slice(5).replace('-', '.')} · ${s.target_label} 기준`;
  // 03칸 오늘 작업 n / 상한
  $('today-count').replaceChildren(
    s ? String(s.videos) : '–',
    el('span', { class: 'slash', text: '/' }),
    `${limit} `,
    el('small', { text: s && s.remaining === 0 ? '건 · 오늘 상한' : '건' }),
  );
}

function recordRow(r) {
  const comment = r.comment_text || (r.action === 'analyze' ? r.reason : '');
  const tone = r.result === 'success' ? 'is-ok' : r.result === 'failure' ? 'is-bad' : 'is-info';
  const showReason = r.reason && (r.result === 'failure' || r.action === 'draft');
  const status = el('td', { class: `st ${tone}`, title: r.reason || null }, [
    el('b', { text: r.status_label }),
    showReason ? el('span', { class: 'st-reason', text: ` · ${r.reason}` }) : null,
  ]);
  const where = [r.profile, r.target_label].filter(Boolean).join(' · ');
  const link = r.video_url
    ? el('a', { href: r.video_url, target: '_blank', rel: 'noopener noreferrer', title: '유튜브에서 영상 보기', 'aria-label': '유튜브에서 영상 보기', text: '↗' })
    : null;
  return el('tr', {}, [
    el('td', { class: 'nowrap', text: formatKst(r.at), title: r.at }),
    el('td', { class: 'clip', text: r.video_title || r.video_id || '–', title: r.video_title || null }),
    el('td', { class: 'nowrap', text: r.action_label }),
    el('td', { class: 'clip', text: comment || '–', title: comment || null }),
    status,
    el('td', { class: 'nowrap', text: where || '–' }),
    el('td', { class: 'link' }, [link]),
  ]);
}

function renderRecords(ops) {
  const body = $('records-body');
  const meta = $('records-meta');
  if (ops.error && !ops.records) {
    body.replaceChildren(el('tr', {}, [el('td', { colspan: '7', class: 'empty-row', text: `기록을 불러오지 못했습니다. ${ops.error.message || ''}` })]));
    return;
  }
  if (!ops.records) return;
  meta.textContent = `최근 ${Math.min(RECENT_ROWS, ops.total)}줄 · 전체 ${ops.total}건 · ACTIVITY ARCHIVE`;
  if (!ops.records.length) {
    body.replaceChildren(el('tr', {}, [el('td', { colspan: '7', class: 'empty-row', text: '아직 기록이 없습니다. 분석 · 초안 생성 · 승인 · 게시가 여기에 시간순(최신이 위)으로 남습니다.' })]));
    return;
  }
  body.replaceChildren(...ops.records.map(recordRow));
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
  const checked = box.querySelector('input[name="mode"]:checked');
  setState({
    ops: {
      target: checked ? checked.value : box.dataset.target || 'sandbox',
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
