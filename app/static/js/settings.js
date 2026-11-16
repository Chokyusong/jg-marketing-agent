// 설정 화면(R2, UI_SPEC 6절). 프로그램 안에서 바꾸고 [저장]하면 바로 적용된다(서버가 서비스를 새 설정으로 다시 만든다).
// - GET /api/settings의 edit(지금 값 · 기본값 · 바꾼 칸 · 범위)로 칸을 그린다. 칸 이름은 app/user_settings.FIELDS와 같다.
// - 바꾼 칸이 있으면 [저장]이 금색(.is-dirty). 저장은 바꾼 칸만 보낸다(PUT /api/settings). 거절되면 칸 옆에 이유.
// - [기본값으로]는 두 번 눌러야 한다(창을 띄우지 않는다). 저장한 API 키는 남는다.
// - API 키는 따로 바로 저장한다(PUT /api/settings/youtube-key). 저장 뒤에는 「저장됨」만 보이고 값은 다시 보이지 않는다.
//   칸에 넣은 값은 보내자마자 지운다. 응답·화면·기록 어디에도 키 값은 없다.
// - 크롬 창 위치는 좌표를 치지 않고 모니터를 고른다(서버가 그 모니터의 안전한 위치를 계산한다).
// - 저장하면 작업 화면의 기본 검색어 · 개수 · 쇼츠 빼기 · 하루 상한 · 글자 수 규칙도 따라 바꾼다(applyWorkDefaults).
// - 바깥 글은 textContent로만 넣는다.
import { api } from './api.js';
import { el } from './format.js';
import { applyDailyMax } from './ops.js';
import { setState } from './state.js';
import { refreshStatus, showScreen } from './topbar.js';

const $ = (id) => document.getElementById(id);

// 칸 이름 → 화면 요소 id
export const FIELD_IDS = {
  'llm.model': 'set-model',
  'comment.min_chars': 'set-min-chars',
  'comment.max_chars': 'set-max-chars',
  'comment.brand': 'set-brand',
  'brand.facts': 'set-facts',
  'comment.disclosure': 'set-disclosure',
  'comment.disclose_default': 'set-disclose-default',
  'limits.daily_max_comments': 'set-daily-max',
  'posting.confirm_before_post': 'set-confirm-before',
  'browser.typing_speed': 'set-typing-speed',
  'browser.window_screen': 'set-window-screen',
  'discover.query': 'set-query',
  'discover.max_results': 'set-max-results',
  'discover.exclude_shorts': 'set-exclude-shorts',
  'discover.shorts_under_seconds': 'set-shorts-seconds',
  // R4
  'transcript.auto': 'set-transcript-auto',
  'llm.warmup_on_start': 'set-warmup-on-start',
  'rising.query': 'set-rising-query',
  'rising.min_views': 'set-rising-min',
  'rising.max_views': 'set-rising-max',
  'rising.min_views_per_hour': 'set-rising-per-hour',
};
const MAX_FACTS = 10;
const RESET_WAIT_MS = 5000;

let data = null; // 마지막 GET/PUT /api/settings 응답
let initial = {}; // 칸을 그릴 때의 값(바뀌었는지 비교)
let models = null; // GET /api/llm/models 응답
let screens = null; // GET /api/screens 응답
let saving = false;
let pendingFocus = null;
let resetArmed = null;
let keyEditing = false;

// ---------------------------------------------------------------- 작은 부품

function label(text, id, key) {
  const changed = data && data.edit && data.edit.changed.includes(key);
  const def = data && data.edit ? data.edit.defaults[key] : undefined;
  return el('dt', {}, [
    el('label', { for: id, text }),
    changed ? el('span', { class: 'tag-changed', title: `기본값: ${shown(def)}`, text: ' · 바꿈' }) : null,
  ]);
}

function shown(value) {
  if (Array.isArray(value)) return value.length ? value.join(' / ') : '없음';
  if (value === true) return '켜짐';
  if (value === false) return '꺼짐';
  return value === '' || value === undefined || value === null ? '없음' : String(value);
}

function errSpan(id) {
  return el('span', { class: 'set-err', id: `err-${id}`, role: 'alert' });
}

function soonTag(key) {
  return data.edit.applies_later.includes(key) ? el('span', { class: 'tag-soon', text: '곧 적용' }) : null;
}

function numberField(key, text, { unit = '', note = '' } = {}) {
  const id = FIELD_IDS[key];
  const [lo, hi] = data.edit.ranges[key] || [];
  const value = data.edit.values[key];
  initial[key] = value;
  return [
    label(text, id, key),
    el('dd', { class: 'set-field' }, [
      el('input', { class: 'field field-num', type: 'number', id, 'data-key': key, inputmode: 'numeric', min: lo, max: hi, step: '1', value: String(value) }),
      unit ? el('span', { class: 'sub', text: unit }) : null,
      note ? el('span', { class: 'caption', text: note }) : null,
      errSpan(id),
    ]),
  ];
}

function textField(key, text, { maxlength = 100, note = '', wide = false } = {}) {
  const id = FIELD_IDS[key];
  const value = data.edit.values[key];
  initial[key] = value;
  return [
    label(text, id, key),
    el('dd', { class: 'set-field' }, [
      el('input', { class: `field field-text${wide ? ' is-wide' : ''}`, type: 'text', id, 'data-key': key, maxlength: String(maxlength), autocomplete: 'off', value }),
      note ? el('span', { class: 'caption', text: note }) : null,
      errSpan(id),
    ]),
  ];
}

function switchField(key, text, onText, offText) {
  const id = FIELD_IDS[key];
  const value = Boolean(data.edit.values[key]);
  initial[key] = value;
  const input = el('input', { type: 'checkbox', id, 'data-key': key, role: 'switch', checked: value });
  const words = el('span', { text: value ? onText : offText });
  input.addEventListener('change', () => { words.textContent = input.checked ? onText : offText; });
  return [
    label(text, id, key),
    el('dd', { class: 'set-field' }, [
      el('label', { class: 'switch' }, [input, el('i', { 'aria-hidden': 'true' }), words]),
      soonTag(key),
      errSpan(id),
    ]),
  ];
}

function readRow(text, value) {
  return [el('dt', { text }), el('dd', {}, [value])];
}

function flag(ok, yes, no) {
  return el('span', { class: `flag ${ok ? 'is-ok' : 'is-bad'}` }, [
    el('i', { class: `dot ${ok ? 'is-ok' : 'is-bad'}`, 'aria-hidden': 'true' }), ok ? yes : no,
  ]);
}

function group(title, id, rows, actions = []) {
  return el('section', { class: 'set-group', id, 'aria-labelledby': `${id}-title` }, [
    el('h3', { id: `${id}-title`, tabindex: '-1', text: title }),
    el('dl', { class: 'set-list set-form' }, rows.flat()),
    actions.length ? el('div', { class: 'set-actions' }, actions) : null,
  ]);
}

// ---------------------------------------------------------------- 유튜브 연결

function keySourceText(source) {
  if (source === 'program') return '프로그램에 저장';
  if (source === 'dev_file') return '개발용 설정 파일에서 읽음';
  return '';
}

function keyRows(s) {
  const y = s.youtube;
  const rows = [];
  if (y.key_configured && !keyEditing) {
    rows.push(readRow('API 키', el('span', { class: 'set-field' }, [
      flag(true, '저장됨', ''),
      el('span', { class: 'caption', id: 'key-source', text: `${keySourceText(y.key_source)} · 값은 보이지 않습니다` }),
    ])));
  } else {
    const input = el('input', {
      class: 'field field-text is-wide', type: 'password', id: 'set-key', autocomplete: 'off', spellcheck: 'false',
      maxlength: '200', placeholder: y.can_store_key ? 'AIza로 시작하는 키를 붙여 넣으세요' : '', disabled: !y.can_store_key,
    });
    input.addEventListener('input', () => $('key-save').classList.toggle('is-dirty', input.value.trim().length > 0));
    input.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); saveKey(); } });
    rows.push([
      el('dt', {}, [el('label', { for: 'set-key', text: 'API 키' })]),
      el('dd', { class: 'set-field' }, [
        input,
        el('button', { type: 'button', class: 'btn btn-small', id: 'key-save', disabled: !y.can_store_key, text: '키 저장' }),
        keyEditing ? el('button', { type: 'button', class: 'btn btn-text btn-small', id: 'key-cancel', text: '취소' }) : null,
        y.can_store_key ? null : el('span', { class: 'caption', text: '이 PC에서는 키를 암호화해 저장할 수 없습니다(Windows에서만 됩니다). 개발용 설정 파일에 YOUTUBE_API_KEY로 넣어 주세요.' }),
      ]),
    ]);
  }
  const q = y.quota;
  rows.push(readRow('오늘 사용량', el('span', { id: 'key-usage', text: `${q.used_today.toLocaleString('ko-KR')} / ${q.daily_limit.toLocaleString('ko-KR')} · 검색 한 번에 100씩 씁니다` })));
  return rows;
}

function keyGuide() {
  const steps = [
    '구글 클라우드 콘솔(console.cloud.google.com)에 구글 계정으로 들어갑니다.',
    '위쪽에서 프로젝트를 하나 만들거나 고릅니다.',
    '「API 및 서비스 → 라이브러리」에서 「YouTube Data API v3」를 찾아 [사용]을 누릅니다.',
    '「사용자 인증 정보 → 사용자 인증 정보 만들기 → API 키」를 누르면 키가 나옵니다.',
    '키를 복사해 위 칸에 붙여 넣고 [키 저장]을 누릅니다. 무료이고 하루에 검색을 100번쯤 할 수 있습니다.',
  ];
  return el('details', { class: 'key-guide', id: 'key-guide' }, [
    el('summary', { text: 'API 키 받는 법' }),
    el('ol', {}, steps.map((t) => el('li', { text: t }))),
  ]);
}

function keyActions(s) {
  const y = s.youtube;
  const out = [];
  if (y.key_configured && !keyEditing) {
    out.push(el('button', { type: 'button', class: 'btn btn-small', id: 'key-change', disabled: !y.can_store_key, text: '바꾸기' }));
    if (y.key_source === 'program') out.push(el('button', { type: 'button', class: 'btn btn-small', id: 'key-delete', text: '지우기' }));
  }
  out.push(el('button', { type: 'button', class: 'btn btn-small', id: 'key-test', text: '연결 확인' }));
  out.push(el('p', { class: 'caption', id: 'key-test-result', role: 'status', 'aria-live': 'polite' }));
  if (y.key_configured && y.key_source === 'dev_file') {
    out.push(el('p', { class: 'caption', text: '개발용 설정 파일의 키는 여기서 지울 수 없습니다. [바꾸기]로 프로그램에 저장하면 그 키를 먼저 씁니다.' }));
  }
  out.push(keyGuide());
  return out;
}

function showKeyResult(text, tone) {
  const node = $('key-test-result');
  if (!node) return;
  node.textContent = text;
  node.className = `caption${tone ? ` ${tone}` : ''}`;
}

async function saveKey() {
  const input = $('set-key');
  if (!input) return;
  const key = input.value.trim();
  input.value = ''; // 보낸 값은 화면에 남기지 않는다
  $('key-save').classList.remove('is-dirty');
  if (!key) {
    showKeyResult('키를 붙여 넣은 뒤 [키 저장]을 누르세요.', 'is-bad');
    return;
  }
  $('key-save').disabled = true;
  try {
    await api.saveKey(key);
    keyEditing = false;
    await load({ keepMessage: true });
    showKeyResult('저장했습니다. 값은 다시 보이지 않습니다. [연결 확인]으로 키가 통하는지 볼 수 있습니다.', 'is-ok');
    refreshStatus();
  } catch (error) {
    if ($('key-save')) $('key-save').disabled = false;
    showKeyResult(`${error.message || ''} ${error.action || ''}`.trim(), 'is-bad');
  }
}

let deleteArmed = null;
async function deleteKey() {
  const button = $('key-delete');
  if (!deleteArmed) {
    button.textContent = '한 번 더 누르면 지웁니다';
    deleteArmed = setTimeout(() => {
      deleteArmed = null;
      if ($('key-delete')) $('key-delete').textContent = '지우기';
    }, RESET_WAIT_MS);
    return;
  }
  clearTimeout(deleteArmed);
  deleteArmed = null;
  button.disabled = true;
  try {
    const res = await api.deleteKey();
    await load({ keepMessage: true });
    showKeyResult(res.key_configured ? '프로그램에 저장한 키를 지웠습니다. 개발용 설정 파일의 키를 씁니다.' : '키를 지웠습니다. 영상을 불러오려면 키를 다시 넣어 주세요.', res.key_configured ? 'is-ok' : '');
    refreshStatus();
  } catch (error) {
    button.disabled = false;
    showKeyResult(`${error.message || ''} ${error.action || ''}`.trim(), 'is-bad');
  }
}

async function testKey() {
  const button = $('key-test');
  button.disabled = true;
  showKeyResult('확인하는 중…', '');
  try {
    const res = await api.testKey();
    showKeyResult(`${res.message} ${res.action || ''}`.trim(), res.ok ? 'is-ok' : 'is-bad');
    const usage = $('key-usage');
    if (usage) usage.textContent = `${res.quota.used_today.toLocaleString('ko-KR')} / ${res.quota.daily_limit.toLocaleString('ko-KR')} · 검색 한 번에 100씩 씁니다`;
  } catch (error) {
    showKeyResult(`${error.message || ''} ${error.action || ''}`.trim(), 'is-bad');
  } finally {
    if ($('key-test')) $('key-test').disabled = false;
  }
}

// ---------------------------------------------------------------- AI 모델

const KIND_NOTE = { code: ' · 코드용(댓글 쓰기에는 덜 맞습니다)', embed: ' · 글을 쓰지 못하는 모델' };

function modelOption(item) {
  const size = item.size_gb ? ` · ${item.size_gb}GB` : '';
  return el('option', { value: item.name, text: `${item.name}${size}${KIND_NOTE[item.kind] || ''}` });
}

function fillModels() {
  const select = $('set-model');
  if (!select || !data) return;
  const current = initial['llm.model'];
  const chosen = select.value || current;
  const items = models && models.reachable ? models.items : [];
  const options = items.map(modelOption);
  if (!items.some((i) => i.name === current)) options.unshift(el('option', { value: current, text: `${current}${models && models.reachable ? ' · 이 PC에 없음' : ''}` }));
  select.replaceChildren(...options);
  select.value = [...select.options].some((o) => o.value === chosen) ? chosen : current;
  paintModelStatus();
  markDirty();
}

function paintModelStatus() {
  const node = $('model-status');
  if (!node || !data) return;
  const select = $('set-model');
  const name = select ? select.value : data.llm.model;
  let tone = 'is-ok';
  let text;
  if (data.llm.error) {
    tone = 'is-bad';
    text = `${data.llm.error.message} ${data.llm.error.action}`.trim();
  } else if (!models) {
    tone = '';
    text = '모델 목록을 읽는 중…';
  } else if (!models.reachable) {
    tone = 'is-bad';
    text = 'AI 프로그램(Ollama)이 꺼져 있어 모델 목록을 읽지 못했습니다. Ollama를 켠 뒤 [모델 확인]을 누르세요.';
  } else if (!models.items.some((i) => i.name === name)) {
    tone = 'is-bad';
    text = `${name} 모델이 이 PC에 없습니다. 목록에서 설치된 모델을 고르거나, 명령 창에서 「ollama pull ${name}」으로 받으세요.`;
  } else {
    const item = models.items.find((i) => i.name === name);
    text = item.kind === 'general' ? '설치돼 있습니다 · 이 PC 안에서 돌아갑니다' : `설치돼 있습니다${KIND_NOTE[item.kind]}`;
    if (item.kind !== 'general') tone = 'is-wait';
  }
  node.className = `flag-line ${tone}`;
  node.textContent = text;
}

async function loadModels() {
  models = null;
  paintModelStatus();
  try {
    models = await api.llmModels();
  } catch {
    models = { reachable: false, items: [], current: '', current_installed: false };
  }
  fillModels();
}

function modelRows(s) {
  const llm = s.llm;
  const current = s.edit.values['llm.model'];
  initial['llm.model'] = current;
  const select = el('select', { id: 'set-model', 'data-key': 'llm.model' }, [el('option', { value: current, text: current })]);
  select.addEventListener('change', paintModelStatus);
  return [
    [label('모델', 'set-model', 'llm.model'), el('dd', { class: 'set-field' }, [select, errSpan('set-model')])],
    readRow('상태', el('span', { id: 'model-status', class: 'flag-line', text: '모델 목록을 읽는 중…' })),
    readRow('지금 모델', el('span', { id: 'model-now', text: `${llm.model || '–'} · ${llm.local ? '이 PC 안에서 돌아갑니다' : '외부 서비스(영상 자료가 그 회사로 갑니다)'}` })),
    readRow('기다리는 시간', `답 하나에 최대 ${Math.round(llm.timeout_seconds)}초 · 모델을 처음 불러올 때는 ${Math.round(llm.cold_timeout_seconds || 420)}초`),
    switchField('llm.warmup_on_start', '켤 때 미리 불러오기', '켜짐 · 프로그램을 켜면 모델을 미리 불러 둡니다', '꺼짐 · 첫 초안 때 불러옵니다'),
  ];
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

// ---------------------------------------------------------------- 댓글 규칙: 써도 되는 사실(줄 더하기 · 빼기)

function factRow(text = '') {
  const input = el('input', { class: 'field field-text is-wide', type: 'text', maxlength: '200', autocomplete: 'off', 'aria-label': '써도 되는 사실 한 줄', value: text });
  const remove = el('button', { type: 'button', class: 'btn btn-text btn-small fact-remove', text: '빼기' });
  const row = el('div', { class: 'fact-row' }, [input, remove]);
  remove.addEventListener('click', () => {
    row.remove();
    paintFactsAdd();
    markDirty();
  });
  return row;
}

function paintFactsAdd() {
  const add = $('facts-add');
  if (add) add.disabled = $('set-facts').querySelectorAll('.fact-row').length >= MAX_FACTS;
}

function factsField(s) {
  const key = 'brand.facts';
  const facts = s.edit.values[key] || [];
  initial[key] = facts;
  const box = el('div', { class: 'facts-edit', id: 'set-facts', 'data-key': key }, facts.map((f) => factRow(f)));
  const add = el('button', { type: 'button', class: 'btn btn-small', id: 'facts-add', text: '줄 더하기' });
  add.addEventListener('click', () => {
    const row = factRow();
    box.append(row);
    row.querySelector('input').focus();
    paintFactsAdd();
    markDirty();
  });
  return [
    el('dt', {}, [el('span', { text: '써도 되는 사실' }), s.edit.changed.includes(key) ? el('span', { class: 'tag-changed', text: ' · 바꿈' }) : null]),
    el('dd', { class: 'set-field is-column' }, [
      box,
      el('div', { class: 'set-field' }, [add, el('span', { class: 'caption', text: `${MAX_FACTS}줄까지 · 홍보하는 곳에 대해 사실인 문장만 씁니다` })]),
      errSpan('set-facts'),
    ]),
  ];
}

// ---------------------------------------------------------------- 게시: 타자 속도 · 모니터

function selectField(key, text, options, value, note = '') {
  const id = FIELD_IDS[key];
  const select = el('select', { id, 'data-key': key }, options.map((o) => el('option', { value: o.value, text: o.label })));
  select.value = value;
  initial[key] = select.value;
  return [
    label(text, id, key),
    el('dd', { class: 'set-field' }, [select, note ? el('span', { class: 'caption', id: `${id}-note`, text: note }) : null, errSpan(id)]),
  ];
}

function screenField(s) {
  const key = 'browser.window_screen';
  const id = FIELD_IDS[key];
  const select = el('select', { id, 'data-key': key }, [el('option', { value: '', text: '모니터를 읽는 중…' })]);
  select.disabled = true;
  select.addEventListener('change', paintScreenNote);
  initial[key] = '';
  return [
    label('크롬 창 띄울 화면', id, key),
    el('dd', { class: 'set-field' }, [select, el('span', { class: 'caption', id: 'set-window-note' }), errSpan(id)]),
  ];
}

function fillScreens() {
  const select = $('set-window-screen');
  if (!select || !data) return;
  const items = screens && screens.checked ? screens.items : [];
  if (!items.length) {
    select.replaceChildren(el('option', { value: '', text: '모니터 정보를 읽지 못했습니다' }));
    select.disabled = true;
    initial['browser.window_screen'] = '';
    $('set-window-note').textContent = `지금 위치 ${data.browser.window_position || '–'}`;
    return;
  }
  const saved = data.edit.values['browser.window_screen'];
  select.replaceChildren(...items.map((m) => el('option', { value: m.id, text: m.label })));
  const pick = items.find((m) => m.id === saved) || items.find((m) => m.current) || null;
  if (!pick) select.prepend(el('option', { value: '', text: `지금 위치(${screens.window_position}) · 모니터 밖` }));
  select.value = pick ? pick.id : '';
  select.disabled = false;
  initial['browser.window_screen'] = select.value;
  paintScreenNote();
  markDirty();
}

function paintScreenNote() {
  const select = $('set-window-screen');
  const note = $('set-window-note');
  if (!select || !note || !screens) return;
  const m = screens.items.find((x) => x.id === select.value);
  note.textContent = m ? `창은 이 화면 왼쪽 위에서 조금 안쪽(${m.position})에 뜹니다` : '';
}

async function loadScreens() {
  try {
    screens = await api.screens();
  } catch {
    screens = { checked: false, items: [], window_position: '' };
  }
  fillScreens();
}

// ---------------------------------------------------------------- 화면 전체

export function settingsView(s) {
  initial = {};
  const b = s.browser;
  return [
    group('유튜브 연결', 'set-youtube', keyRows(s), keyActions(s)),
    group('AI 모델', 'set-ai', modelRows(s), [
      el('button', { type: 'button', class: 'btn btn-small', id: 'models-refresh', text: '모델 확인' }),
      el('button', { type: 'button', class: 'btn btn-small', id: 'warmup-btn', text: '미리 불러오기' }),
      el('p', { class: 'caption', id: 'warmup-note', text: '모델을 미리 메모리에 올려 두면 첫 초안이 빨리 나옵니다.' }),
    ]),
    group('댓글 규칙', 'set-comment', [
      numberField('comment.min_chars', '최소 글자 수', { unit: '자' }),
      numberField('comment.max_chars', '최대 글자 수', { unit: '자 (광고 표기 포함)' }),
      textField('comment.brand', '홍보하는 곳', { maxlength: 30 }),
      factsField(s),
      textField('comment.disclosure', '광고 표기 문구', { maxlength: 20, note: '켜면 댓글이 이 글로 시작합니다' }),
      switchField('comment.disclose_default', '광고 표기 기본값', '켜짐 · 새 초안에 광고 표기를 붙입니다', '꺼짐 · 새 초안을 광고 표기 없이 만듭니다'),
    ]),
    group('게시', 'set-post', [
      numberField('limits.daily_max_comments', '하루 상한', { unit: '개 (1~50)', note: '③에서는 낮추기만 됩니다' }),
      switchField('posting.confirm_before_post', '게시 직전 확인', '켜짐 · 입력 뒤 [게시]를 한 번 더 누릅니다', '꺼짐 · [댓글 달기] 한 번으로 게시까지'),
      selectField('browser.typing_speed', '타자 속도', s.edit.typing_speeds, s.edit.values['browser.typing_speed']),
      screenField(s),
      readRow('크롬', flag(b.chrome_found, '찾음', '못 찾음 · 크롬을 설치해 주세요')),
      readRow('자동 입력', flag(b.playwright_ready, '준비됨', '설치되지 않음 · 댓글을 달 수 없습니다')),
      readRow('처음 연습 모드', b.default_target === 'sandbox' ? '켜짐' : '꺼짐'),
    ]),
    group('영상 찾기', 'set-discover', [
      textField('discover.query', '기본 검색어', { maxlength: 100, wide: true }),
      numberField('discover.max_results', '기본 개수', { unit: '개 (1~50)' }),
      switchField('discover.exclude_shorts', '쇼츠 빼기', '켜짐 · 짧은 영상은 목록에서 뺍니다', '꺼짐'),
      numberField('discover.shorts_under_seconds', '쇼츠 길이', { unit: '초보다 짧으면 쇼츠', note: '기본 181초(3분 1초)' }),
      switchField('transcript.auto', '자막 자동으로 읽기', '켜짐 · 영상을 고르면 자막을 읽습니다. 못 읽으면 제목·설명으로', '꺼짐 · 직접 넣은 자막만 씁니다'),
    ]),
    group('뜨기 직전 영상', 'set-rising', [
      textField('rising.query', '검색어', { maxlength: 100, note: '올린 지 34시간 안의 영상에서 찾습니다' }),
      numberField('rising.min_views', '조회수 최소', { unit: '회' }),
      numberField('rising.max_views', '조회수 최대', { unit: '회' }),
      numberField('rising.min_views_per_hour', '시간당 조회수', { unit: '회 이상' }),
      readRow('댓글', '이 목록에서 고른 영상은 초안까지만 만듭니다'),
    ]),
    el('p', { class: 'caption set-version', text: `버전 ${s.version}` }),
  ];
}

// 칸의 지금 값(서버에 보낼 모양)
function controlValue(node) {
  const key = node.dataset.key;
  if (key === 'brand.facts') return [...node.querySelectorAll('.fact-row input')].map((i) => i.value.trim()).filter(Boolean);
  if (node.type === 'checkbox') return node.checked;
  if (node.type === 'number') {
    const raw = node.value.trim();
    return /^-?\d+$/.test(raw) ? Number(raw) : raw;
  }
  return node.tagName === 'SELECT' ? node.value : node.value.trim();
}

function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function changedValues() {
  const out = {};
  for (const node of document.querySelectorAll('#settings-body [data-key]')) {
    const key = node.dataset.key;
    if (node.disabled || !(key in initial)) continue;
    const value = controlValue(node);
    if (key === 'browser.window_screen' && !value) continue;
    if (!same(value, initial[key])) out[key] = value;
  }
  return out;
}

function markDirty() {
  const save = $('settings-save');
  const dirty = Boolean(data) && Object.keys(changedValues()).length > 0;
  save.disabled = !dirty || saving;
  save.classList.toggle('is-dirty', dirty);
  const kind = $('settings-msg').dataset.kind || '';
  if (dirty && !['error', 'busy', 'armed'].includes(kind)) setMessage('바꾼 값이 있습니다 · [저장]을 누르면 바로 적용됩니다', '', 'dirty');
  else if (!dirty && kind === 'dirty') setMessage('', '');
}

function setMessage(text, tone, kind = '') {
  const node = $('settings-msg');
  node.textContent = text;
  node.className = `set-msg${tone ? ` ${tone}` : ''}`;
  node.dataset.kind = kind;
}

function clearErrors() {
  for (const node of document.querySelectorAll('#settings-body .set-err')) node.textContent = '';
  for (const node of document.querySelectorAll('#settings-body .is-bad[data-key], #settings-body .field.is-bad')) node.classList.remove('is-bad');
}

function showErrors(fields) {
  let first = null;
  const general = [];
  for (const [key, reason] of Object.entries(fields || {})) {
    const id = FIELD_IDS[key];
    const span = id ? $(`err-${id}`) : null;
    if (!span) {
      general.push(reason);
      continue;
    }
    span.textContent = reason;
    const control = $(id);
    if (control && control.classList.contains('field')) control.classList.add('is-bad');
    if (!first) first = control;
  }
  if (first && first.focus) first.focus();
  return general;
}

function render(s) {
  data = s;
  const body = $('settings-body');
  body.replaceChildren(...settingsView(s));
  $('warmup-btn').addEventListener('click', warmup);
  $('models-refresh').addEventListener('click', loadModels);
  if ($('key-save')) $('key-save').addEventListener('click', saveKey);
  if ($('key-cancel')) $('key-cancel').addEventListener('click', () => { keyEditing = false; render(data); });
  if ($('key-change')) $('key-change').addEventListener('click', () => { keyEditing = true; render(data); $('set-key').focus(); });
  if ($('key-delete')) $('key-delete').addEventListener('click', deleteKey);
  $('key-test').addEventListener('click', testKey);
  if (models) fillModels();
  if (screens) fillScreens();
  markDirty();
  applyFocus();
}

// 그 칸이 지금 없으면(키를 이미 저장함 등) 그 묶음의 제목으로
const FOCUS_GROUP = { 'set-key': 'set-youtube-title', 'set-model': 'set-ai-title' };

function applyFocus() {
  if (!pendingFocus) return;
  const node = $(pendingFocus) || $(FOCUS_GROUP[pendingFocus] || '');
  if (!node) return;
  pendingFocus = null;
  const target = node.disabled ? node.closest('.set-group').querySelector('h3') : node;
  target.scrollIntoView({ block: 'nearest' });
  target.focus({ preventScroll: true });
}

// 시작 준비 상자에서: 설정 화면을 열고 그 칸으로
export function focusSetting(id) {
  pendingFocus = id;
  showScreen('settings');
}

async function load({ keepMessage = false } = {}) {
  const body = $('settings-body');
  body.setAttribute('aria-busy', 'true');
  if (!keepMessage) setMessage('', '');
  try {
    render(await api.settings());
    loadModels();
    loadScreens();
  } catch (error) {
    data = null;
    $('settings-save').disabled = true;
    body.replaceChildren(
      el('p', { class: 'checks-error', text: `설정을 불러오지 못했습니다 · ${error.message || ''}` }),
      error.action ? el('p', { class: 'caption', text: error.action }) : null,
      el('p', { class: 'caption', text: '다른 화면에 갔다가 다시 열면 다시 불러옵니다.' }),
    );
  } finally {
    body.setAttribute('aria-busy', 'false');
  }
}

async function save() {
  const changes = changedValues();
  if (!Object.keys(changes).length || saving) return;
  saving = true;
  clearErrors();
  $('settings-save').disabled = true;
  setMessage('저장하는 중…', '', 'busy');
  try {
    const res = await api.saveSettings(changes);
    render(res);
    applyWorkDefaults(res);
    setMessage('저장했습니다 · 바로 적용됐습니다', 'is-ok', 'done');
    refreshStatus();
    loadModels();
  } catch (error) {
    const general = showErrors(error.fields);
    const why = general.length ? ` ${general.join(' ')}` : '';
    setMessage(`${error.message || ''}${why} ${error.action || ''}`.trim(), 'is-bad', 'error');
  } finally {
    saving = false;
    markDirty(); // 거절된 뒤에도 바꾼 값은 칸에 남아 있다(이유 문구는 덮지 않는다)
  }
}

async function reset() {
  const button = $('settings-reset');
  if (!resetArmed) {
    button.textContent = '한 번 더 누르면 기본값으로';
    setMessage('프로그램에서 바꾼 값을 모두 처음 값으로 되돌립니다. 저장한 API 키는 남습니다.', '', 'armed');
    resetArmed = setTimeout(() => {
      resetArmed = null;
      button.textContent = '기본값으로';
      if ($('settings-msg').dataset.kind === 'armed') setMessage('', '');
    }, RESET_WAIT_MS);
    return;
  }
  clearTimeout(resetArmed);
  resetArmed = null;
  button.textContent = '기본값으로';
  button.disabled = true;
  clearErrors();
  try {
    const res = await api.resetSettings();
    render(res);
    applyWorkDefaults(res);
    setMessage('기본값으로 돌렸습니다 · 저장한 API 키는 그대로입니다', 'is-ok', 'done');
    refreshStatus();
    loadModels();
  } catch (error) {
    setMessage(`${error.message || ''} ${error.action || ''}`.trim(), 'is-bad', 'error');
  } finally {
    button.disabled = false;
  }
}

// ---------------------------------------------------------------- 작업 화면에 바로 반영

function selectedDefault(select) {
  const option = [...select.options].find((o) => o.defaultSelected);
  return option ? option.value : select.value;
}

// 저장한 기본값을 작업 화면 칸에 넣는다. 사람이 그 칸을 이미 바꿨으면(기본값과 다르면) 건드리지 않는다.
export function applyWorkDefaults(s) {
  const d = s.discover;
  const q = $('q');
  if (q.value === q.defaultValue) q.value = d.query;
  q.defaultValue = d.query;

  const count = $('max-results');
  const before = selectedDefault(count);
  const keep = count.value !== before ? count.value : String(d.max_results);
  const numbers = [...new Set([10, 20, d.max_results])].sort((a, b) => a - b);
  count.replaceChildren(...numbers.map((n) => {
    const option = el('option', { value: String(n), text: `${n}개` });
    option.defaultSelected = n === d.max_results;
    return option;
  }));
  count.value = numbers.map(String).includes(keep) ? keep : String(d.max_results);

  const shorts = $('exclude-shorts');
  if (shorts) {
    if (shorts.checked === shorts.defaultChecked) shorts.checked = d.exclude_shorts;
    shorts.defaultChecked = d.exclude_shorts;
  }

  const box = $('draft-box');
  box.dataset.disclosure = s.comment.disclosure;
  const values = (s.edit && s.edit.values) || {};
  if (typeof values['comment.disclose_default'] === 'boolean') {
    box.dataset.discloseDefault = String(values['comment.disclose_default']);
  }
  const exec = document.querySelector('.exec-settings');
  if (exec && typeof values['posting.confirm_before_post'] === 'boolean') {
    exec.dataset.confirm = String(values['posting.confirm_before_post']);
  }
  box.dataset.min = String(s.comment.min_chars);
  box.dataset.max = String(s.comment.max_chars);

  applyDailyMax(s.daily_max_comments);
  setState({}); // 글자 수 표시 등을 새 규칙으로 다시 그린다
}

export function initSettings() {
  const body = $('settings-body');
  body.addEventListener('input', markDirty);
  body.addEventListener('change', markDirty);
  $('settings-save').addEventListener('click', save);
  $('settings-reset').addEventListener('click', reset);
  document.addEventListener('screen:show', (event) => {
    if (event.detail === 'settings') {
      keyEditing = false;
      load();
    }
  });
}
