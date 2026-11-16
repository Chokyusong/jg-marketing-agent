// 02 댓글 초안(6단계): 사람이 직접 쓰는 글 상자. 입력이 0.4초 멈추면 POST /api/validate로 V1~V11을
// 검사해 글자 수·통과 요약·실패 목록을 그린다. AI 초안(5단계, loadDraft)은 서버가 검사한 결과를
// 그대로 보이고, 사람이 고치면 같은 검사를 다시 한다.
// 높이를 아끼려고 통과한 항목은 한 줄 요약으로 접고, 실패한 항목만 문구와 함께 펼친다.
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

// 서버와 같은 셈: NFC로 맞추고 앞뒤 공백을 뺀 코드 포인트 수(표기 포함).
export function countChars(text) {
  return [...text.normalize('NFC').trim()].length;
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
  const n = countChars(text);
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
    const result = await api.validate(videoId, text);
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

function checksView(state) {
  const text = $('draft-text').value;
  const v = resultFor(state);
  if (!state.selectedId) {
    return [el('p', { class: 'checks-idle', text: '영상을 고르고 초안을 쓰면 규칙 검사(V1~V11)를 합니다.' })];
  }
  if (state.validationError) {
    return [
      el('p', { class: 'checks-error', text: `검사하지 못했습니다 · ${state.validationError.message || ''}` }),
      state.validationError.action ? el('p', { class: 'checks-idle', text: state.validationError.action }) : null,
    ];
  }
  if (!hasDraft(text)) {
    return [el('p', { class: 'checks-idle', text: '초안을 쓰고 입력을 멈추면 규칙 검사(V1~V11)를 합니다.' })];
  }
  if (!v) return [el('p', { class: 'checks-idle', text: '규칙 검사 중…' })];

  const { result } = v;
  const passed = result.checks.filter((c) => c.passed);
  const failed = result.checks.filter((c) => !c.passed);
  const label = failed.length
    ? `규칙 검사 · ${result.total}개 중 ${result.passed_count}개 통과`
    : `규칙 검사 · ${result.total}개 모두 통과`;
  const summary = el('details', { class: `checks-pass${failed.length ? '' : ' is-all'}`, open: passOpen }, [
    el('summary', { text: label }),
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
  input.disabled = !state.selectedId || Boolean(state.run && state.run.videoId === state.selectedId && !['done', 'error'].includes(state.run.phase));
  const v = resultFor(state);
  const fresh = v && v.text === input.value;
  const checked = Boolean(fresh && v.result.passed);
  const approved = isApproved(state);
  const tag = $('draft-tag');
  tag.textContent = approved ? 'APPROVED · 승인됨' : checked ? 'CHECKED' : 'DRAFT · REVIEW REQUIRED';
  tag.classList.toggle('is-ok', checked || approved);
  const d = state.draft && state.draft.video_id === state.selectedId ? state.draft : null;
  $('draft-tone').textContent = d && d.tone_label ? `말투 · ${d.tone_label}` : '';

  const checks = $('draft-checks');
  checks.replaceChildren(...checksView(state).filter(Boolean));
  checks.classList.toggle('is-stale', Boolean(v && !fresh && hasDraft(input.value)));
  checks.setAttribute('aria-busy', String(Boolean(state.validationLoading)));
}

function resetFor(videoId) {
  clearTimeout(timer);
  seq += 1;
  $('draft-text').value = videoId ? `${disclosure()} ` : '';
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

export function initDraft() {
  const input = $('draft-text');
  input.addEventListener('input', () => {
    paintMirror();
    fitHeight();
    paintCount();
    render(getState()); // 이름표·흐림을 바로 바꾼다(검사는 입력이 멈추면)
    schedule();
  });
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
