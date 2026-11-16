// 다음 행동 하나만 강조(9단계, R1). 처음 보는 사람이 "지금 무엇을 누르면 되는지"를 화면 하나로 알게 한다.
// - 화면 상태를 보고 지금 누를 것 하나를 고른다(nextAction). 그 요소에만 .is-next를 붙이고(단추면 금색 채움)
//   위 줄 「다음: …」에 같은 안내를 쓴다. 누를 것이 없으면(만드는 중·게시 중) 아무것도 강조하지 않는다.
// - 순서: [영상 불러오기] → 목록에서 하나 고르기(고르면 초안이 자동으로) → [댓글 달기]
//   → (서버가 게시 직전에 기다리면) [게시] / 직접 게시하는 영상이면 [게시했어요] → 다른 영상 고르기.
// - 다른 칸이 단추를 다 그린 뒤에 돌도록 app.js에서 맨 마지막에 init 한다.
import { draftText } from './draft.js';
import { startBlocker, STATE_WORDS } from './job.js';
import { isRunning } from './report.js';
import { getState, selectedVideo, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const NO_CONCERN = 'no_love_concern';
export const WAIT_HINT = '처음에는 1분쯤 걸릴 수 있습니다';

const running = (job) => Boolean(job && !job.finished);

function draftFor(state) {
  const d = state.draft;
  return d && d.video_id === state.selectedId ? d : null;
}

function checkResult(state) {
  const v = state.validation;
  if (!v || v.videoId !== state.selectedId || v.text !== draftText()) return null;
  return v.result;
}

// { id: 강조할 요소 id | null, hint: 위 줄에 쓸 안내 }
export function nextAction(state) {
  const job = state.job;
  if (running(job)) {
    if (job.waiting_for === 'approve') {
      const where = job.target === 'sandbox' ? '연습 페이지에' : '유튜브에';
      return { id: 'job-primary', hint: `다음: [게시]를 누르면 ${where} 댓글을 올립니다` };
    }
    if (job.waiting_for === 'confirm') return { id: 'job-primary', hint: '크롬에서 직접 게시한 뒤 [게시했어요]를 누르세요' };
    return { id: null, hint: `댓글 다는 중 · ${STATE_WORDS[job.state] || job.state_label}` };
  }
  if (state.jobBusy) return { id: null, hint: '댓글 달 준비 중…' };
  if (!state.videos.length) {
    if (state.loading) return { id: null, hint: '영상을 불러오는 중…' };
    return { id: 'search-btn', hint: '다음: [영상 불러오기]를 누르세요' };
  }
  const video = selectedVideo();
  if (!video) return { id: 'video-list', hint: '다음: 목록에서 영상을 하나 고르세요' };
  if (isRunning(state)) return { id: null, hint: `댓글 초안을 만드는 중 · ${WAIT_HINT}` };

  const ctx = state.context && state.context.video_id === state.selectedId ? state.context : null;
  if (state.runError && state.runError.kind === NO_CONCERN && !(ctx && ctx.transcript_source === 'manual')) {
    const pasted = $('transcript-text') && $('transcript-text').value.trim();
    return pasted
      ? { id: 'transcript-save', hint: '다음: 넣은 자막을 [저장]하세요' }
      : { id: 'transcript-paste', hint: '다음: 「자막 직접 넣기」에 자막을 붙여 넣으세요' };
  }
  const draft = draftFor(state);
  if (!draft) {
    if (state.runError) return { id: 'run-btn', hint: '다음: [다시 해 보기]를 누르세요' };
    return { id: null, hint: '댓글 초안을 기다리는 중' };
  }
  const blocker = startBlocker(state);
  if (!blocker) {
    const failed = job && job.finished && job.state === 'failed' && job.video_id === video.video_id;
    return { id: 'job-primary', hint: failed ? '다음: [다시 시도]를 누르세요' : '다음: 초안을 읽고 [댓글 달기]를 누르세요' };
  }
  const target = state.ops ? state.ops.target : 'sandbox';
  if (video.commented && video.commented[target]) return { id: 'video-list', hint: '댓글을 단 영상입니다 · 다음: 다른 영상을 고르세요' };
  const result = checkResult(state);
  if (result && !result.passed) return { id: 'draft-edit', hint: '빨간 항목을 고치거나 [다른 댓글 만들기]를 누르세요' };
  return { id: null, hint: blocker };
}

let lastId = null;

function usable(node) {
  return Boolean(node) && !node.disabled;
}

function paint() {
  const state = getState();
  const next = nextAction(state);
  const node = next.id ? $(next.id) : null;
  const id = usable(node) ? next.id : null;
  if (id !== lastId) {
    for (const old of document.querySelectorAll('.is-next')) old.classList.remove('is-next');
    if (id) node.classList.add('is-next');
    lastId = id;
  } else if (id && !node.classList.contains('is-next')) {
    node.classList.add('is-next'); // 그 칸이 요소를 다시 만들었을 때
  }
  document.body.dataset.next = id || '';
  const hint = $('next-hint');
  if (hint.textContent !== next.hint) hint.textContent = next.hint;
}

export function initNext() {
  subscribe(paint);
  // 글을 고치거나 자막을 붙여 넣는 순간(검사·저장 전에도) 다시 고른다
  for (const id of ['draft-text', 'transcript-text']) $(id).addEventListener('input', paint);
  // 단추의 disabled는 다른 칸이 상태와 함께 바꾸므로, 잠깐 뒤 한 번 더 맞춘다(타이머로 바뀌는 단추)
  setInterval(paint, 1000);
}
