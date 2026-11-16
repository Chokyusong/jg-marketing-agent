// 기록 · 프로필 · 설정 화면(R1). 3판의 겹침 패널(설정 보기, 기록 전체 보기)을 화면으로 옮겼다.
// - 화면을 열 때마다 새로 불러온다(topbar.js의 'screen:show'). 작업 화면의 상태는 건드리지 않는다.
// - 기록: GET /api/records?limit=200. 거르기 전체 / 게시 / 실패. 실패 줄에는 이유와 [화면 캡처], 게시 줄에는 [유튜브에서 보기].
// - 프로필: GET /api/status의 프로필 폴더 + GET /api/profiles(대상별 마지막 사용). 로그인 단추는 곧 연결(R2).
// - 설정: GET /api/settings를 보기만 한다(키 값·경로 없음). 저장·바꾸기는 곧 연결(R2). [미리 불러오기]는 지금도 된다.
// - 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { el, targetName } from './format.js';
import { formatKst, resultText, toneOf, whereText } from './ops.js';
import { getState, subscribe } from './state.js';
import { showScreen } from './topbar.js';

const $ = (id) => document.getElementById(id);
const ALL_ROWS = 200; // /api/records의 최대
const SOON = '곧 연결됩니다';

function soonButton(text, cls = 'btn btn-small') {
  return el('button', { type: 'button', class: cls, disabled: true, title: SOON }, [text, el('span', { class: 'soon', text: '곧 연결' })]);
}

// ---------------------------------------------------------------- 기록 화면

let allRecords = null;

function filterValue() {
  const checked = document.querySelector('input[name="records-filter"]:checked');
  return checked ? checked.value : 'all';
}

function fullRow(r) {
  const tone = toneOf(r);
  const showReason = r.reason && (r.result === 'failure' || r.action === 'draft');
  const status = el('td', { class: `st wrap ${tone}` }, [
    el('b', { text: resultText(r) }),
    showReason ? el('span', { class: 'st-reason', text: ` · ${r.reason}` }) : null,
  ]);
  const links = [];
  if (r.has_screenshot && r.job_id) {
    links.push(el('a', { href: `/api/jobs/${encodeURIComponent(r.job_id)}/screenshot`, target: '_blank', rel: 'noopener', text: '화면 캡처' }));
  }
  if (r.video_url && r.action === 'post' && r.result === 'success' && r.target === 'youtube') {
    links.push(el('a', { href: r.video_url, target: '_blank', rel: 'noopener noreferrer', text: '유튜브에서 보기' }));
  } else if (r.video_url) {
    links.push(el('a', { href: r.video_url, target: '_blank', rel: 'noopener noreferrer', text: '영상 보기' }));
  }
  return el('tr', { class: tone }, [
    el('td', { class: 'nowrap', text: formatKst(r.at), title: r.at }),
    el('td', { class: 'wrap', text: r.video_title || r.video_id || '–' }),
    el('td', { class: 'nowrap', text: whereText(r) || '–' }),
    el('td', { class: 'wrap', text: r.comment_text || (r.action === 'analyze' ? r.reason : '') || '–' }),
    status,
    el('td', {}, [el('span', { class: 'links' }, links)]),
  ]);
}

function renderAll() {
  const body = $('records-all-body');
  const meta = $('records-all-meta');
  if (!allRecords) return;
  const filter = filterValue();
  const items = allRecords.items.filter((r) => (filter === 'post' ? r.action === 'post' : filter === 'failure' ? r.result === 'failure' : true));
  const failures = allRecords.items.filter((r) => r.result === 'failure').length;
  const shown = allRecords.items.length < allRecords.total ? ` · 최근 ${allRecords.items.length}건만 보입니다` : '';
  meta.textContent = `전체 ${allRecords.total}건 · 실패 ${failures}건${shown} · 최신이 위`;
  if (!items.length) {
    const text = filter === 'failure' ? '실패한 기록이 없습니다.' : filter === 'post' ? '아직 게시 기록이 없습니다.' : '아직 기록이 없습니다. 초안 만들기와 게시가 여기에 남습니다.';
    body.replaceChildren(el('tr', {}, [el('td', { colspan: '6', class: 'empty-row', text })]));
    return;
  }
  body.replaceChildren(...items.map(fullRow));
}

async function loadRecords() {
  $('records-all-meta').textContent = '불러오는 중…';
  try {
    allRecords = await api.records(ALL_ROWS);
    renderAll();
  } catch (error) {
    allRecords = null;
    $('records-all-meta').textContent = '기록을 불러오지 못했습니다';
    $('records-all-body').replaceChildren(el('tr', {}, [el('td', { colspan: '6', class: 'empty-row', text: `${error.message || ''} ${error.action || ''}`.trim() })]));
  }
}

// ---------------------------------------------------------------- 프로필 화면

let lastUsed = {}; // 프로필 이름 → { sandbox, youtube } 마지막 사용 시각

function profileCard(p) {
  const used = lastUsed[p.name] || {};
  const times = ['youtube', 'sandbox'].filter((t) => used[t]).map((t) => `${formatKst(used[t])} (${targetName(t)})`);
  return el('section', { class: 'card', 'aria-label': p.name }, [
    el('h3', { text: p.name }),
    el('p', { class: 'card-line' }, [
      el('i', { class: `dot ${p.exists ? 'is-ok' : 'is-wait'}`, 'aria-hidden': 'true' }),
      p.exists ? '준비됨 · 이 프로필 전용 크롬 폴더가 있습니다' : '아직 없음 · 처음 쓸 때 만듭니다',
    ]),
    el('p', { class: 'card-line' }, [el('i', { class: 'dot is-off', 'aria-hidden': 'true' }), '로그인 여부 · 곧 확인할 수 있습니다']),
    el('p', { class: 'card-line', text: `마지막으로 쓴 때 · ${times.length ? times.join(', ') : '없음'}` }),
    el('div', { class: 'card-actions' }, [soonButton('로그인하기'), soonButton('로그인 확인'), soonButton('유튜브 열기')]),
  ]);
}

function renderProfiles(state) {
  const body = $('profiles-body');
  const b = state.browser;
  if (!b) {
    body.replaceChildren(el('p', { class: 'empty', text: '프로필 정보를 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.' }));
    return;
  }
  const notes = [];
  if (!b.chrome_found) notes.push(el('p', { class: 'alert-msg', text: '이 PC에서 크롬을 찾지 못했습니다. 크롬을 설치해 주세요.' }));
  body.replaceChildren(...notes, ...b.profiles.map(profileCard));
}

async function loadProfiles() {
  renderProfiles(getState());
  try {
    const [sandbox, youtube] = await Promise.all([api.profiles('sandbox'), api.profiles('youtube')]);
    lastUsed = {};
    for (const [target, list] of [['sandbox', sandbox], ['youtube', youtube]]) {
      for (const p of list.items) {
        if (!lastUsed[p.name]) lastUsed[p.name] = {};
        if (p.last_used_at) lastUsed[p.name][target] = p.last_used_at;
      }
    }
    renderProfiles(getState());
  } catch {
    // 마지막 사용 시각을 못 받아도 카드는 보인다
  }
}

// ---------------------------------------------------------------- 설정 화면

function row(label, value, extra = null) {
  return [el('dt', { text: label }), el('dd', {}, [value, extra])];
}

function flag(ok, yes, no) {
  return el('span', { class: `flag ${ok ? 'is-ok' : 'is-bad'}` }, [
    el('i', { class: `dot ${ok ? 'is-ok' : 'is-bad'}`, 'aria-hidden': 'true' }), ok ? yes : no,
  ]);
}

function group(title, rows, actions = []) {
  return el('section', { class: 'set-group' }, [
    el('h3', { text: title }),
    el('dl', { class: 'set-list' }, rows.flat()),
    actions.length ? el('div', { class: 'set-actions' }, actions) : null,
  ]);
}

export function settingsView(s) {
  const c = s.comment;
  const b = s.browser;
  const llm = s.llm;
  const q = s.youtube.quota;
  const facts = s.brand_facts.length
    ? el('ul', { class: 'facts' }, s.brand_facts.map((f) => el('li', { text: f })))
    : '없음(홍보하는 곳에 대한 사실 문장을 쓰지 않습니다)';
  const model = llm.error
    ? flag(false, '', `${llm.error.message} ${llm.error.action}`.trim())
    : `${llm.model || '–'} · ${llm.local ? '이 PC 안에서 돌아갑니다' : '외부 서비스(영상 자료가 그 회사로 갑니다)'}`;
  const where = b.window_position_adjusted ? ` · 화면 밖이라 ${b.window_position_used || '가운데'}에 띄웁니다` : '';
  const warmNote = el('p', { class: 'caption', id: 'warmup-note', text: '모델을 미리 메모리에 올려 두면 첫 초안이 빨리 나옵니다.' });
  return [
    group('유튜브 연결', [
      row('API 키', flag(s.youtube.key_configured, '저장됨 (값은 보이지 않습니다)', '없음 · 영상을 불러올 수 없습니다')),
      row('오늘 사용량', `${q.used_today.toLocaleString('ko-KR')} / ${q.daily_limit.toLocaleString('ko-KR')} · 검색 한 번에 100씩 씁니다`),
    ], [soonButton('바꾸기'), soonButton('지우기'), soonButton('연결 확인')]),
    group('AI 모델', [
      row('지금 모델', model),
      row('기다리는 시간', `답 하나에 최대 ${Math.round(llm.timeout_seconds)}초`),
      row('읽는 자료 길이', `${llm.context_chars.toLocaleString('ko-KR')}자까지`),
    ], [el('button', { type: 'button', class: 'btn btn-small', id: 'warmup-btn' }, ['미리 불러오기']), soonButton('모델 바꾸기'), warmNote]),
    group('댓글 규칙', [
      row('글자 수', `${c.min_chars}~${c.max_chars}자 (광고 표기 포함)`),
      row('광고 표기', el('span', { class: 'gold', text: c.disclosure }), ' 로 시작'),
      row('내 채널 영상', c.own_video_count
        ? `${c.own_video_count}개 · 이 영상에서만 광고 표기를 끌 수 있습니다`
        : '등록된 영상 없음 · 모든 영상에 광고 표기를 붙입니다'),
      row('홍보하는 곳', c.brand),
      row('써도 되는 사실', facts),
    ]),
    group('게시', [
      row('하루 상한', `${s.daily_max_comments}개 (③에서는 낮추기만 됩니다)`),
      row('영상당 댓글', '1개 (같은 영상에는 다시 달지 않습니다)'),
      row('처음 연습 모드', b.default_target === 'sandbox' ? '켜짐' : '꺼짐'),
      row('크롬', flag(b.chrome_found, '찾음', '못 찾음 · 크롬을 설치해 주세요')),
      row('자동 입력', flag(b.playwright_ready, '준비됨', '설치되지 않음 · 연습 모드를 쓸 수 없습니다')),
      row('입력 속도', `글자마다 ${b.typing_delay_ms[0]}~${b.typing_delay_ms[1]}ms`),
      row('크롬 창 위치', `${b.window_position}${where}`),
    ]),
    group('영상 찾기', [
      row('기본 검색어', s.discover.query),
      row('기본 개수', `${s.discover.max_results}개`),
      row('쇼츠 빼기', s.discover.exclude_shorts ? '켜짐 · 짧은 영상은 목록에서 뺍니다' : '꺼짐'),
      row('자막', s.transcript_provider === 'manual' ? '직접 넣은 자막만' : '자동으로 읽고, 못 읽으면 제목·설명으로'),
    ]),
    el('p', { class: 'caption', text: `버전 ${s.version}` }),
  ];
}

async function loadSettings() {
  const body = $('settings-body');
  body.setAttribute('aria-busy', 'true');
  try {
    const data = await api.settings();
    body.replaceChildren(...settingsView(data));
    $('warmup-btn').addEventListener('click', warmup);
  } catch (error) {
    body.replaceChildren(
      el('p', { class: 'checks-error', text: `설정을 불러오지 못했습니다 · ${error.message || ''}` }),
      error.action ? el('p', { class: 'caption', text: error.action }) : null,
      el('p', { class: 'caption', text: '다른 화면에 갔다가 다시 열면 다시 불러옵니다.' }),
    );
  } finally {
    body.setAttribute('aria-busy', 'false');
  }
}

let warming = false;
async function warmup() {
  if (warming) return;
  warming = true;
  const button = $('warmup-btn');
  const started = Date.now();
  const note = () => $('warmup-note');
  button.disabled = true;
  button.textContent = '불러오는 중…';
  const tick = setInterval(() => {
    if (note()) note().textContent = `모델을 메모리에 올리는 중… ${Math.round((Date.now() - started) / 1000)}초 · 큰 모델은 1~2분 걸릴 수 있습니다`;
  }, 1000);
  try {
    const res = await api.warmup();
    if (note()) note().textContent = `불러왔습니다 · ${res.model} · ${res.seconds.toFixed(1)}초. 이제 초안이 바로 시작됩니다.`;
  } catch (error) {
    if (note()) note().textContent = `불러오지 못했습니다 · ${error.message || ''} ${error.action || ''}`.trim();
  } finally {
    clearInterval(tick);
    warming = false;
    if ($('warmup-btn')) {
      $('warmup-btn').disabled = false;
      $('warmup-btn').textContent = '미리 불러오기';
    }
  }
}

// ----------------------------------------------------------------

export function initScreens() {
  for (const radio of document.querySelectorAll('input[name="records-filter"]')) radio.addEventListener('change', renderAll);
  $('records-all').addEventListener('click', () => showScreen('records', { focus: true }));
  document.addEventListener('screen:show', (event) => {
    if (event.detail === 'records') loadRecords();
    else if (event.detail === 'profiles') loadProfiles();
    else if (event.detail === 'settings') loadSettings();
  });
  // 프로필 화면을 보고 있는 동안 상태가 바뀌면(30초마다) 카드도 따라 바꾼다
  let lastBrowser = null;
  subscribe((state) => {
    if (state.screen !== 'profiles' || state.browser === lastBrowser) return;
    lastBrowser = state.browser;
    renderProfiles(state);
  });
}
