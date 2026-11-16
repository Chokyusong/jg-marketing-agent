// 겹침 패널 두 개(9단계): SETTINGS(읽기 전용 설정값, [모델 미리 불러오기])와 작업 기록 전체(VIEW ALL).
// - 브라우저의 <dialog>(showModal)를 쓴다: 뒤 화면은 눌리지 않고 Esc로 닫힌다.
//   열면 패널 제목으로 초점이 들어가고, 닫으면 연 단추로 초점이 돌아간다.
// - 설정은 GET /api/settings(키 값·경로 없음), 전체 기록은 GET /api/records?limit=200.
// - [모델 미리 불러오기]는 POST /api/llm/warmup을 누를 때만 부른다(패널을 연다고 부르지 않는다).
// - 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { el } from './format.js';
import { formatKst } from './ops.js';

const $ = (id) => document.getElementById(id);
const ALL_ROWS = 200; // /api/records의 최대

const openers = new Map(); // 패널 → 연 단추(닫으면 초점을 돌려준다)

export function openPanel(panel, opener) {
  if (panel.open) return;
  openers.set(panel, opener || document.activeElement);
  panel.showModal();
  const title = panel.querySelector('h2[tabindex]');
  (title || panel).focus();
}

function closePanel(panel) {
  if (panel.open) panel.close();
}

function setupPanel(panel) {
  for (const button of panel.querySelectorAll('[data-close]')) {
    button.addEventListener('click', () => closePanel(panel));
  }
  // 패널 바깥(어두운 배경)을 누르면 닫는다
  panel.addEventListener('click', (event) => {
    if (event.target === panel) closePanel(panel);
  });
  panel.addEventListener('close', () => {
    const opener = openers.get(panel);
    openers.delete(panel);
    if (opener && typeof opener.focus === 'function' && opener.isConnected) opener.focus();
  });
}

// ---------------------------------------------------------------- SETTINGS

function row(label, value, extra = null) {
  return [el('dt', { text: label }), el('dd', {}, [value, extra])];
}

function flag(ok, yes, no) {
  return el('span', { class: `flag ${ok ? 'is-ok' : 'is-bad'}` }, [
    el('i', { class: `dot ${ok ? 'is-ok' : 'is-bad'}`, 'aria-hidden': 'true' }), ok ? yes : no,
  ]);
}

function group(title, en, rows) {
  return el('section', { class: 'set-group' }, [
    el('h3', {}, [title, ' ', el('small', { text: en })]),
    el('dl', { class: 'set-list' }, rows.flat()),
  ]);
}

export function settingsView(s) {
  const c = s.comment;
  const b = s.browser;
  const llm = s.llm;
  const facts = s.brand_facts.length
    ? el('ul', { class: 'facts' }, s.brand_facts.map((f) => el('li', { text: f })))
    : '없음(운명원에 대한 사실 문장을 쓰지 않습니다)';
  const where = b.window_position_adjusted
    ? el('span', { class: 'warn', text: ` → 실제 ${b.window_position_used || '가운데'} · ${b.window_position_note}` })
    : el('span', { class: 'sub', text: b.window_position_checked ? ' · 모니터 안' : ' · 모니터 정보를 읽지 못해 그대로 씀' });
  const model = llm.error
    ? flag(false, '', `${llm.error.message} ${llm.error.action}`.trim())
    : `${llm.model || '–'} · ${llm.local ? '로컬(이 PC 안)' : '외부(영상 자료가 그 회사로 갑니다)'}`;
  return [
    group('댓글 규칙', 'COMMENT', [
      row('글자 수', `${c.min_chars}~${c.max_chars}자 (표기 포함)`),
      row('홍보 표기', el('span', { class: 'gold', text: c.disclosure }), ' 로 시작'),
      row('브랜드', c.brand),
      row('브랜드 사실', facts),
    ]),
    group('운영 한도', 'LIMITS', [
      row('하루 상한', `${s.daily_max_comments}건 (화면에서는 낮추기만 됩니다)`),
      row('기본 작업 방식', b.default_target_label),
      row('영상당 댓글', '1개 (같은 영상은 다시 열지 않습니다)'),
    ]),
    group('프로필', 'PROFILES', s.profiles.map((p) => row(p.name, flag(p.ready, `폴더 준비됨 · ${p.folder}`, `폴더 없음 · ${p.folder} (처음 실행 때 만듭니다)`)))),
    group('AI 모델', 'LLM', [
      row('공급자', `${llm.active}${llm.type && llm.type !== llm.active ? ` (${llm.type})` : ''}`),
      row('모델', model),
      row('기다리는 시간', `답 하나에 최대 ${Math.round(llm.timeout_seconds)}초 · 모델 유지 ${llm.keep_alive}`),
      row('자료 길이 한도', `${llm.context_chars.toLocaleString('ko-KR')}자`),
    ]),
    group('브라우저', 'BROWSER', [
      row('크롬', flag(b.chrome_found, '찾음', '못 찾음 · 크롬을 설치하거나 config.yaml의 browser.chrome_path')),
      row('자동 실행', flag(b.playwright_ready, 'Playwright 있음', 'Playwright 없음 · 테스트 페이지 자동 실행 불가')),
      row('창 위치', `설정 ${b.window_position}`, where),
      row('창 보이기', b.headless ? '창 없이(headless)' : '창을 띄움'),
      row('입력 속도', `글자마다 ${b.typing_delay_ms[0]}~${b.typing_delay_ms[1]}ms`),
    ]),
    group('YouTube', 'DATA API', [
      row('API 키', flag(s.youtube.key_configured, '있음 (값은 보이지 않습니다)', '없음 · .env의 YOUTUBE_API_KEY')),
      row('할당량', `오늘 ${s.youtube.quota.used_today.toLocaleString('ko-KR')} / ${s.youtube.quota.daily_limit.toLocaleString('ko-KR')} 단위 · 검색 1회 100단위`),
      row('기본 검색어', `${s.discover.query} · ${s.discover.max_results}개${s.discover.exclude_shorts ? ' · 쇼츠 제외' : ''}`),
      row('자막', s.transcript_provider === 'manual' ? '붙여 넣은 자막만' : s.transcript_provider),
    ]),
    el('p', { class: 'caption set-version', text: `V ${s.version} · ${s.stage}단계` }),
  ];
}

async function loadSettings() {
  const body = $('settings-body');
  body.setAttribute('aria-busy', 'true');
  try {
    const data = await api.settings();
    body.replaceChildren(...settingsView(data));
  } catch (error) {
    body.replaceChildren(
      el('p', { class: 'checks-error', text: `설정을 불러오지 못했습니다 · ${error.message || ''}` }),
      error.action ? el('p', { class: 'caption', text: error.action }) : null,
      el('p', { class: 'caption', text: '패널을 닫았다가 다시 열면 다시 불러옵니다.' }),
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
  const note = $('warmup-note');
  const started = Date.now();
  button.disabled = true;
  button.textContent = '불러오는 중…';
  const tick = setInterval(() => {
    note.textContent = `모델을 메모리에 올리는 중… ${Math.round((Date.now() - started) / 1000)}초 · 큰 모델은 1~2분 걸릴 수 있습니다`;
  }, 1000);
  try {
    const res = await api.warmup();
    note.textContent = `불러옴 · ${res.provider} · ${res.model} · ${res.seconds.toFixed(1)}초. 이제 분석이 바로 시작됩니다.`;
  } catch (error) {
    note.textContent = `불러오지 못했습니다 · ${error.message || ''} ${error.action || ''}`.trim();
  } finally {
    clearInterval(tick);
    warming = false;
    button.disabled = false;
    button.textContent = '모델 미리 불러오기 ↗';
  }
}

// ---------------------------------------------------------------- VIEW ALL

let allRecords = null;

function fullRow(r) {
  const comment = r.comment_text || (r.action === 'analyze' ? r.reason : '');
  const tone = r.result === 'success' ? 'is-ok' : r.result === 'failure' ? 'is-bad' : 'is-info';
  const status = el('td', { class: `st wrap ${tone}`, 'data-label': '상태' }, [
    el('b', { text: r.status_label }),
    r.reason ? el('span', { class: 'st-reason', text: ` · ${r.reason}` }) : null,
  ]);
  const shot = r.has_screenshot && r.job_id
    ? el('a', { href: `/api/jobs/${encodeURIComponent(r.job_id)}/screenshot`, target: '_blank', rel: 'noopener', text: '캡처 ↗', title: '실패 화면 캡처 보기' })
    : null;
  const link = r.video_url
    ? el('a', { href: r.video_url, target: '_blank', rel: 'noopener noreferrer', title: '유튜브에서 영상 보기', 'aria-label': '유튜브에서 영상 보기', text: '↗' })
    : null;
  // data-label: 휴대폰 폭에서 표가 카드로 바뀔 때 칸 이름으로 보인다(style.css)
  return el('tr', { class: tone }, [
    el('td', { class: 'nowrap', 'data-label': '시간', text: formatKst(r.at), title: r.at }),
    el('td', { class: 'wrap', 'data-label': '영상', text: r.video_title || r.video_id || '–' }),
    el('td', { class: 'nowrap', 'data-label': '작업', text: r.action_label }),
    el('td', { class: 'wrap', 'data-label': '댓글', text: comment || '–' }),
    status,
    el('td', { class: 'nowrap', 'data-label': '프로필', text: [r.profile, r.target_label].filter(Boolean).join(' · ') || '–' }),
    el('td', { class: 'link' }, shot ? [shot] : []),
    el('td', { class: 'link' }, link ? [link] : []),
  ]);
}

function renderAll() {
  const body = $('records-all-body');
  const meta = $('records-all-meta');
  if (!allRecords) return;
  const failedOnly = $('records-failed-only').checked;
  const items = failedOnly ? allRecords.items.filter((r) => r.result === 'failure') : allRecords.items;
  const failures = allRecords.items.filter((r) => r.result === 'failure').length;
  const shown = allRecords.items.length < allRecords.total ? ` · 최근 ${allRecords.items.length}건만 보입니다` : '';
  meta.textContent = `전체 ${allRecords.total}건 · 실패 ${failures}건${shown} · 최신이 위`;
  if (!items.length) {
    body.replaceChildren(el('tr', {}, [el('td', { colspan: '8', class: 'empty-row', text: failedOnly ? '실패한 기록이 없습니다.' : '아직 기록이 없습니다. 분석 · 초안 생성 · 승인 · 게시가 여기에 남습니다.' })]));
    return;
  }
  body.replaceChildren(...items.map(fullRow));
}

async function loadAll() {
  $('records-all-meta').textContent = '불러오는 중…';
  try {
    allRecords = await api.records(ALL_ROWS);
    renderAll();
  } catch (error) {
    allRecords = null;
    $('records-all-meta').textContent = '기록을 불러오지 못했습니다';
    $('records-all-body').replaceChildren(el('tr', {}, [el('td', { colspan: '8', class: 'empty-row', text: `${error.message || ''} ${error.action || ''} 닫았다가 다시 열어 주세요.`.trim() })]));
  }
}

export function initPanels() {
  const settings = $('settings-panel');
  const records = $('records-panel');
  setupPanel(settings);
  setupPanel(records);
  $('settings-open').addEventListener('click', (event) => {
    document.getElementById('nav').classList.remove('is-open');
    $('menu-toggle').setAttribute('aria-expanded', 'false');
    openPanel(settings, $('nav').contains(event.currentTarget) && getComputedStyle($('menu-toggle')).display !== 'none'
      ? $('menu-toggle') : event.currentTarget);
    loadSettings();
  });
  $('warmup-btn').addEventListener('click', warmup);
  $('records-all').addEventListener('click', (event) => {
    openPanel(records, event.currentTarget);
    loadAll();
  });
  $('records-failed-only').addEventListener('change', renderAll);
}
