// ② 댓글 초안(6단계): 사람이 고칠 수 있는 글 상자. 입력이 0.4초 멈추면 POST /api/validate로 V1~V14을
// 검사해 글자 수·통과 요약·실패 목록을 그린다. AI 초안(5단계, loadDraft)은 서버가 검사한 결과를
// 그대로 보이고, 사람이 고치면 같은 검사를 다시 한다.
// 높이를 아끼려고 통과한 항목은 한 줄 요약으로 접고, 실패한 항목만 문구와 함께 펼친다.
// R3: 「광고 표기 붙이기」는 모든 영상에서 켜고 끈다. 처음 상태는 설정의 「광고 표기 기본값」.
// 초안이 있으면 서버가 저장된 글에서 표기만 붙이거나 떼고 다시 검사한다(AI를 다시 부르지 않는다).
import { api } from './api.js';
import { el } from './format.js';
import { getState, setState, subscribe } from './state.js';

const DEBOUNCE_MS = 400;
const $ = (id) => document.getElementById(id);

let timer = null;
let seq = 0;
let lastSelected = null;
let lastContextKey = null;
let passOpen = false; // 통과 요약을 펼쳐 두었는지(다시 그려도 유지)
let waitingForContext = false; // 맥락을 모으는 중이라 검사를 미뤘는지

const box = () => $('draft-box');
const disclosure = () => box().dataset.disclosure || '[광고]';

// 「광고 표기 붙이기」 체크
export function discloseOn() {
  const c = $('disclose');
  return !c || c.checked;
}

// 새 영상을 고를 때의 처음 상태: 설정의 「광고 표기 기본값」(바꾸면 GET /api/status로 바로 온다)
export function discloseDefault(state = getState()) {
  if (state.browser && typeof state.browser.disclose_default === 'boolean') return state.browser.disclose_default;
  return box().dataset.discloseDefault !== 'false';
}

let toggleSeq = 0;

// 체크를 바꾸면 글 상자 맨 앞의 표기를 붙이거나 뗀다(그 뒤 다시 검사).
function applyDisclosure(on) {
  const input = $('draft-text');
  const mark = disclosure();
  const text = input.value;
  if (on && !text.startsWith(mark)) input.value = `${mark} ${text.trimStart()}`;
  if (!on && text.startsWith(mark)) input.value = text.slice(mark.length).trimStart();
}

// 서버와 같은 셈: NFC로 맞추고 앞뒤 공백을 뺀 코드 포인트 수. 홍보 표기와 그 뒤 한 칸은 세지
// 않는다(2026-11-18 대표: 「[광고]는 빼고 120자」, 규칙 검사 V1과 같다).
export function countChars(text, mark = '') {
  let t = text.normalize('NFC').trim();
  if (mark && t.startsWith(mark)) t = t.slice(mark.length).trimStart();
  return [...t].length;
}

// 표기만 있거나 비어 있으면 아직 쓴 글이 없는 것으로 본다(검사하지 않는다).
function hasDraft(text) {
  const rest = text.trim();
  return rest !== '' && rest !== disclosure();
}

// 글 상자 뒤에 같은 글을 그리고 표기 부분만 금색으로 칠한다(글 상자 글자는 투명).
function paintMirror() {
  const text = $('draft-text').value;
  const mark = disclosure();
  const parts = text.split(mark);
  const nodes = [];
  parts.forEach((part, i) => {
    if (part) nodes.push(document.createTextNode(part));
    if (i < parts.length - 1) nodes.push(el('span', { class: 'disclosure', text: mark }));
  });
  nodes.push(document.createTextNode('​')); // 끝 줄바꿈도 같은 높이로
  $('draft-mirror').replaceChildren(...nodes);
}

function fitHeight() {
  const input = $('draft-text');
  input.style.height = 'auto';
  input.style.height = `${input.scrollHeight + 2}px`;
}

function paintCount() {
  const text = $('draft-text').value;
  const n = countChars(text, disclosure());
  const min = Number(box().dataset.min || 40);
  const max = Number(box().dataset.max || 120);
  const count = $('draft-count');
  count.textContent = `${n} / ${max}자`;
  count.classList.toggle('is-over', hasDraft(text) && (n < min || n > max));
}

function resultFor(state) {
  const v = state.validation;
  if (!v || v.videoId !== state.selectedId) return null;
  return v;
}

// 글 상자의 글이 AI 초안 그대로면 서버가 초안을 만들 때 한 검사 결과를 쓴다(근거 구절 기준).
function draftResult(state, text) {
  const d = state.draft;
  return d && d.video_id === state.selectedId && d.body === text ? d.validation : null;
}

async function runCheck() {
  const state = getState();
  const videoId = state.selectedId;
  const text = $('draft-text').value;
  if (!videoId || !hasDraft(text)) return;
  const known = draftResult(state, text);
  if (known) {
    seq += 1;
    setState({ validation: { videoId, text, result: known }, validationLoading: false, validationError: null });
    return;
  }
  if (state.contextLoading && !state.context) {
    waitingForContext = true; // 맥락이 오면(또는 실패하면) 다시 부른다. 인기 댓글을 두 번 부르지 않게
    return;
  }
  const mine = ++seq;
  if (!state.validationLoading) setState({ validationLoading: true });
  try {
    const result = await api.validate(videoId, text, discloseOn());
    if (mine !== seq || getState().selectedId !== videoId) return;
    setState({ validation: { videoId, text, result }, validationLoading: false, validationError: null });
  } catch (error) {
    if (mine !== seq || getState().selectedId !== videoId) return;
    setState({ validation: null, validationLoading: false, validationError: error });
  }
}

function schedule() {
  clearTimeout(timer);
  if (!hasDraft($('draft-text').value)) {
    seq += 1; // 오던 응답은 버린다
    setState({ validation: null, validationLoading: false, validationError: null });
    return;
  }
  timer = setTimeout(runCheck, DEBOUNCE_MS);
}

// 2026-11-18 AI 검수 한 번: 「규칙 검사 · 14개 모두 통과」 옆 한 줄. 글 상자의 글이 검수한 그 초안
// 그대로일 때만 보인다(사람이 고치면 그 글의 검수가 아니다). 어색하다고 했으면 문제 한 줄을 붙인다
// (넘치면 말줄임, 전체는 마우스를 올리면). 게시는 막지 않는다
// 2026-11-18: 「검수 불완전」(판정 칸이 빠진 답)은 초록 통과와 다르게 경고색
const REVIEW_CLASS = {
  passed: 'is-ok', rewritten: 'is-ok', flagged: 'is-warn', error: 'is-dim', incomplete: 'is-warn',
};

function reviewView(state, text) {
  const d = state.draft;
  const review = d && d.video_id === state.selectedId && d.body === text ? d.review : null;
  if (!review || !review.label) return null;
  const problem = review.status === 'flagged' && review.problems && review.problems[0];
  const line = problem ? `${review.label} · ${problem}` : review.label;
  // 이야기 방식의 맥락 일치 검증(2026-11-18): 「맥락 검증 못 함」은 통과(초록)와 다르게 경고색,
  // 「맥락 확인 필요」는 벗어난 문장을 까닭 줄에 먼저 보인다(서버가 맨 앞에 둔다)
  const kind = review.story && review.status === 'error' ? 'is-warn' : (REVIEW_CLASS[review.status] || '');
  return el('span', { class: `checks-review ${kind}`, id: 'checks-review', title: line, text: line });
}

function checksView(state) {
  const text = $('draft-text').value;
  const v = resultFor(state);
  if (!state.selectedId) {
    return [el('p', { class: 'checks-idle', text: '영상을 고르면 초안을 만들고 규칙 검사를 합니다.' })];
  }
  if (state.validationError) {
    return [
      el('p', { class: 'checks-error', text: `검사하지 못했습니다 · ${state.validationError.message || ''}` }),
      state.validationError.action ? el('p', { class: 'checks-idle', text: state.validationError.action }) : null,
    ];
  }
  if (!hasDraft(text)) {
    return [el('p', { class: 'checks-idle', text: '초안이 나오면(또는 직접 쓰고 입력을 멈추면) 규칙 검사를 합니다.' })];
  }
  if (!v) return [el('p', { class: 'checks-idle', text: '규칙 검사 중…' })];

  const { result } = v;
  const passed = result.checks.filter((c) => c.passed);
  const failed = result.checks.filter((c) => !c.passed);
  const label = failed.length
    ? `규칙 검사 · ${result.total}개 중 ${result.passed_count}개 통과`
    : `규칙 검사 · ${result.total}개 모두 통과`;
  const summary = el('details', { class: `checks-pass${failed.length ? '' : ' is-all'}`, open: passOpen }, [
    el('summary', {}, [el('span', { text: label }), reviewView(state, text)]),
    el('p', { text: passed.map((c) => `${c.code} ${c.name}`).join(' · ') || '통과한 항목 없음' }),
  ]);
  summary.addEventListener('toggle', () => { passOpen = summary.open; });
  const list = failed.length
    ? el('ul', { class: 'checks-fail', 'aria-label': '걸린 항목' }, failed.map((c) =>
      el('li', {}, [el('b', { text: `${c.code} ${c.name}` }), el('span', { text: c.message })])))
    : null;
  return [summary, list];
}

// 지금 글 상자의 글이 승인한 초안 그대로인지
export function isApproved(state) {
  const d = state.draft;
  const input = $('draft-text');
  return Boolean(d && d.video_id === state.selectedId && d.status === 'approved' && input && d.body === input.value);
}

function render(state) {
  const input = $('draft-text');
  const job = state.job;
  const posting = Boolean(job && !job.finished) || state.jobBusy; // 게시 중에는 글을 바꾸지 않는다
  input.disabled = !state.selectedId || posting
    || Boolean(state.run && state.run.videoId === state.selectedId && !['done', 'error'].includes(state.run.phase));
  // 2026-11-18 「다듬는 중」: 잠긴 글 상자에 규칙 검사를 통과한 초안이 들어 있다. 읽을 수 있게 덜 흐리게
  $('draft-edit').classList.toggle('is-reviewing', Boolean(input.disabled && state.run
    && state.run.videoId === state.selectedId && state.run.phase === 'review'));
  const v = resultFor(state);
  const fresh = v && v.text === input.value;
  const checked = Boolean(fresh && v.result.passed);
  const approved = isApproved(state);
  const tag = $('draft-tag');
  tag.textContent = approved ? '승인됨' : checked ? '검사 통과' : '검토 필요';
  tag.classList.toggle('is-ok', checked || approved);
  const d = state.draft && state.draft.video_id === state.selectedId ? state.draft : null;
  $('draft-tone').textContent = d && d.tone_label ? `말투 · ${d.tone_label}` : '';
  $('draft-tone').hidden = !(d && d.tone_label);
  $('disclose').disabled = input.disabled; // 어떤 영상이든 켜고 끌 수 있다(게시 중에는 잠근다)

  const checks = $('draft-checks');
  checks.replaceChildren(...checksView(state).filter(Boolean));
  checks.classList.toggle('is-stale', Boolean(v && !fresh && hasDraft(input.value)));
  checks.setAttribute('aria-busy', String(Boolean(state.validationLoading)));
}

function resetFor(videoId) {
  clearTimeout(timer);
  seq += 1;
  toggleSeq += 1;
  const on = discloseDefault(); // 영상을 바꾸면 설정의 「광고 표기 기본값」으로 시작한다
  $('disclose').checked = on;
  $('draft-text').value = videoId && on ? `${disclosure()} ` : '';
  paintMirror();
  fitHeight();
  paintCount();
  setState({ validation: null, validationLoading: false, validationError: null, draft: null });
}

// AI 초안(5단계)을 글 상자에 넣는다. 검사 결과는 서버가 초안을 만들 때 한 것을 그대로 쓴다.
export function loadDraft(draft) {
  clearTimeout(timer);
  seq += 1;
  const input = $('draft-text');
  input.value = draft.body;
  $('disclose').checked = draft.disclosed !== false;
  paintMirror();
  fitHeight();
  paintCount();
  setState({
    draft,
    validation: { videoId: draft.video_id, text: draft.body, result: draft.validation },
    validationLoading: false,
    validationError: null,
  });
}

export function draftText() {
  return $('draft-text').value;
}

// 켬/끔을 바꿨다: 글 상자에서 바로 붙이거나 떼고, 초안이 있으면 서버에도 알린다
// (저장된 글에서 표기만 바꾸고 다시 검사 — AI를 다시 부르지 않는다. 길이가 넘치면 검사에 걸린 채로 온다)
async function onDiscloseChange(on) {
  const before = $('draft-text').value;
  applyDisclosure(on);
  paintMirror();
  fitHeight();
  paintCount();
  render(getState());
  const state = getState();
  const d = state.draft && state.draft.video_id === state.selectedId ? state.draft : null;
  if (!d || d.status === 'superseded') {
    schedule();
    return;
  }
  const mine = ++toggleSeq;
  const videoId = d.video_id;
  const applied = $('draft-text').value;
  try {
    const next = await api.setDisclosure(d.id, on);
    if (mine !== toggleSeq || getState().selectedId !== videoId) return;
    // 사람이 고친 글이 아직 저장 전이면(켜기 전에 고쳤거나, 저장을 기다리는 사이에 고쳤으면)
    // 글 상자의 글을 그대로 둔다
    const edited = before !== d.body || $('draft-text').value !== applied;
    if (!edited) loadDraft(next);
    else {
      setState({ draft: next });
      schedule();
    }
  } catch (error) {
    if (mine !== toggleSeq || getState().selectedId !== videoId) return;
    setState({ validationError: error });
  }
}

export function initDraft() {
  const input = $('draft-text');
  input.addEventListener('input', () => {
    paintMirror();
    fitHeight();
    paintCount();
    render(getState()); // 이름표·흐림을 바로 바꾼다(검사는 입력이 멈추면)
    schedule();
  });
  $('disclose').addEventListener('change', (event) => { onDiscloseChange(event.target.checked); });
  paintMirror();
  paintCount();
  // 창 너비가 바뀌면 줄바꿈이 달라지므로 높이를 다시 맞춘다(높이 변화에는 반응하지 않는다).
  let lastWidth = 0;
  new ResizeObserver(([entry]) => {
    const width = Math.round(entry.contentRect.width);
    if (width !== lastWidth) {
      lastWidth = width;
      fitHeight();
    }
  }).observe(input);

  subscribe((state) => {
    if (state.selectedId !== lastSelected) {
      lastSelected = state.selectedId;
      lastContextKey = null;
      waitingForContext = false;
      resetFor(state.selectedId);
      return; // resetFor가 setState로 다시 그린다
    }
    // 맥락이 새로 오거나 자막이 바뀌면(근거가 달라진다) 쓴 글을 다시 검사한다.
    const ctx = state.context && state.context.video_id === state.selectedId ? state.context : null;
    const key = ctx ? `${ctx.video_id}|${ctx.built_at}|${ctx.transcript_chars}` : null;
    if (waitingForContext && !state.contextLoading) {
      waitingForContext = false;
      lastContextKey = key;
      if (hasDraft(input.value)) runCheck();
    } else if (key !== lastContextKey) {
      lastContextKey = key;
      if (key && hasDraft(input.value)) {
        clearTimeout(timer);
        runCheck();
      }
    }
    render(state);
  });
}
