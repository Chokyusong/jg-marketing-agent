// ② 영상 자료(3단계): 영상을 고르면 맥락을 만들고 「자막」·「인기 댓글」 줄을 실제 값으로 그린다.
// R4: 자막은 자동으로 읽는다("자동으로 읽은 자막 3,210자(한국어, 자동 생성)"). 못 읽으면 이유와 함께
// "제목과 설명으로 대신합니다". 「자막 직접 넣기」는 자동으로 못 읽었을 때(또는 직접 넣은 자막이 있을 때)만 보인다.
// 「자막 직접 넣기」에 넣고 [저장]하면 자막이 "붙여 넣은 자막 n자"로 바뀌고, 'transcript:saved'를 알린다
// (초안이 아직 없으면 report.js가 그 자막으로 다시 만든다).
import { api } from './api.js';
import { getState, setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const n = (value) => Number(value || 0).toLocaleString('ko-KR');

let lastSelected = null;

// 응답이 왔을 때 사용자가 그새 다른 영상을 골랐으면 버린다.
async function run(videoId, call, { fill = true, saved = false } = {}) {
  setState({ contextLoading: true, contextError: null });
  try {
    const data = await call();
    if (getState().selectedId !== videoId) return;
    if (fill) $('transcript-text').value = data.transcript_text || '';
    setState({ context: data, contextLoading: false, quota: data.quota });
    updateCount();
    if (saved) document.dispatchEvent(new CustomEvent('transcript:saved', { detail: videoId }));
  } catch (error) {
    if (getState().selectedId !== videoId) return;
    setState({ contextLoading: false, contextError: error });
  }
}

function load(videoId) {
  $('transcript-text').value = '';
  setState({ context: null });
  return run(videoId, () => api.buildContext(videoId));
}

export function transcriptLine(ctx) {
  if (ctx.transcript_source === 'manual') return `붙여 넣은 자막 ${n(ctx.transcript_chars)}자`;
  if (ctx.transcript_source === 'auto') {
    const label = ctx.transcript_label ? `(${ctx.transcript_label})` : '';
    return `자동으로 읽은 자막 ${n(ctx.transcript_chars)}자${label}`;
  }
  if (ctx.transcript_source === 'unofficial') return `비공식 조회 자막 ${n(ctx.transcript_chars)}자`;
  // 2026-11-18 자료가 얇은 영상: 자막이 없으면 무엇만 읽었는지와 초안이 밋밋할 수 있다는 것을 알린다
  if (ctx.material === 'thin') {
    // 자료 부족: 자막도 없고 설명·댓글도 거의 없어 제목뿐(서버 `context.material_state`)
    const lead = ctx.transcript_reason === 'off' ? '자막 자동 읽기가 꺼져 있고'
      : ctx.transcript_reason ? `자막을 읽지 못했고(${ctx.transcript_note || '이유 모름'})`
        : '자막이 없고';
    return `자료 부족: ${lead} 설명·댓글도 거의 없어 제목만 읽었습니다. ${THIN_NOTE}`;
  }
  if (ctx.transcript_reason === 'off') return `자막 자동 읽기가 꺼져 있어 제목·설명·댓글만 읽었습니다. ${THIN_NOTE}`;
  if (ctx.transcript_reason) {
    return `자막을 읽지 못해(${ctx.transcript_note || '이유 모름'}) 제목·설명·댓글만 읽었습니다. ${THIN_NOTE}`;
  }
  return `자막이 없어 제목·설명·댓글만 읽었습니다. ${THIN_NOTE}`;
}
const THIN_NOTE = '초안이 밋밋할 수 있어요';

function commentsLine(ctx) {
  if (ctx.comments_disabled) return '댓글이 막힌 영상';
  if (!ctx.comment_count) return '인기 댓글 없음';
  return `인기 댓글 ${n(ctx.comment_count)}개`;
}

function noteLine(ctx) {
  if (!ctx.truncated) return '';
  if (ctx.transcript_truncated) {
    return `자막이 길어 AI에는 앞부분과 뒷부분만 넣습니다(가운데 줄임, 한도 ${n(ctx.context_chars)}자).`;
  }
  return `설명·댓글이 길어 AI에는 일부만 넣습니다(한도 ${n(ctx.context_chars)}자).`;
}

function updateCount() {
  const box = $('transcript-text');
  const max = Number(box.dataset.max || 20000);
  const len = box.value.length;
  const count = $('transcript-count');
  count.textContent = `${n(len)} / ${n(max)}자`;
  count.classList.toggle('is-over', len > max);
  const state = getState();
  $('transcript-save').disabled = !state.selectedId || state.contextLoading || !box.value.trim();
}

function render(state) {
  const ctx = state.context && state.context.video_id === state.selectedId ? state.context : null;
  const transcript = $('ctx-transcript');
  const comments = $('ctx-comments');
  transcript.classList.remove('is-warn');

  if (!state.selectedId) {
    transcript.textContent = '영상을 고르면 표시됩니다.';
    comments.textContent = '–';
  } else if (state.contextLoading && !ctx) {
    transcript.textContent = '자막 읽는 중…';
    comments.textContent = '인기 댓글 불러오는 중…';
  } else if (ctx) {
    transcript.textContent = transcriptLine(ctx);
    transcript.classList.toggle('is-warn', ctx.transcript_source === 'none');
    comments.textContent = commentsLine(ctx);
  } else {
    transcript.textContent = '–';
    comments.textContent = '–';
  }

  // 넓은 화면에서는 두 줄을 한 줄에 말줄임으로 둔다(2026-11-17). 전체는 마우스를 올리면
  transcript.title = transcript.textContent;
  comments.title = comments.textContent;

  const note = ctx ? noteLine(ctx) : '';
  $('ctx-note').textContent = note;
  $('ctx-note').hidden = !note;

  const errorBox = $('context-error');
  if (state.selectedId && state.contextError) {
    $('context-error-msg').textContent = state.contextError.message || '요청을 처리하지 못했습니다.';
    $('context-error-action').textContent = state.contextError.action || '';
    errorBox.hidden = false;
  } else {
    errorBox.hidden = true;
  }

  // R4: 자동으로 읽은 자막이 있으면 「자막 직접 넣기」를 숨긴다(못 읽었을 때의 보조)
  const paste = $('transcript-paste');
  const pasteHidden = Boolean(ctx && ctx.transcript_source === 'auto');
  if (paste.hidden !== pasteHidden) paste.hidden = pasteHidden;
  const hint = $('transcript-paste-hint');
  if (hint) hint.hidden = !(ctx && ctx.transcript_source === 'none');

  $('transcript-text').disabled = !state.selectedId || state.contextLoading;
  const clear = $('transcript-clear');
  clear.hidden = !(ctx && ctx.transcript_source === 'manual');
  clear.disabled = state.contextLoading;
  $('transcript-save').textContent = state.contextLoading && ctx ? '저장 중…' : '저장';
  $('context-box').setAttribute('aria-busy', String(state.contextLoading));
  updateCount();
}

export function initContext() {
  $('transcript-text').addEventListener('input', updateCount);
  $('transcript-save').addEventListener('click', () => {
    const videoId = getState().selectedId;
    const text = $('transcript-text').value;
    if (!videoId || !text.trim()) return;
    run(videoId, () => api.saveTranscript(videoId, text), { saved: true });
  });
  $('transcript-clear').addEventListener('click', () => {
    const videoId = getState().selectedId;
    if (!videoId) return;
    // 글 상자는 비우지 않는다(다시 [저장]하면 되돌릴 수 있게).
    run(videoId, () => api.clearTranscript(videoId), { fill: false });
  });

  subscribe((state) => {
    if (state.selectedId !== lastSelected) {
      lastSelected = state.selectedId;
      if (state.selectedId) {
        load(state.selectedId);
        return; // load가 setState로 다시 그린다
      }
      $('transcript-text').value = '';
      setState({ context: null, contextLoading: false, contextError: null });
      return;
    }
    render(state);
  });
}
