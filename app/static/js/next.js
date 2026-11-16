// 다음 행동 하나만 강조(9단계). 처음 보는 사람이 "지금 무엇을 누르면 되는지"를 화면 하나로 알게 한다.
// - 화면 상태를 보고 지금 누를 것 하나를 고른다(nextAction). 그 요소에만 .is-next(금색 채움)를 붙이고
//   흐름 띠의 지금 단계 설명 줄에 같은 안내를 쓴다. 누를 것이 없으면(진행 중) 아무것도 강조하지 않는다.
// - 순서: [영상 찾기] → 목록에서 하나 고르기 → [분석하고 초안 만들기] → [이 초안 승인]
//   → [브라우저에서 영상 열기] → [게시 승인](테스트 페이지) / [게시했어요](실제 유튜브) → 다른 영상 고르기.
// - 다른 칸이 단추를 다 그린 뒤에 돌도록 app.js에서 맨 마지막에 init 한다.
import { isApproved } from './draft.js';
import { startBlocker } from './job.js';
import { getState, selectedVideo, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const NO_CONCERN = 'no_love_concern';
export const WAIT_HINT = '분석·초안은 1~2분쯤 걸립니다';

const running = (job) => Boolean(job && !job.finished);
const analyzing = (state) => Boolean(state.run && state.run.videoId === state.selectedId
  && !['done', 'error'].includes(state.run.phase));

function draftFor(state) {
  const d = state.draft;
  return d && d.video_id === state.selectedId ? d : null;
}

function checkResult(state) {
  const v = state.validation;
  const input = $('draft-text');
  if (!v || v.videoId !== state.selectedId || !input || v.text !== input.value) return null;
  return v.result;
}

// { id: 강조할 요소 id | null, hint: 흐름 띠에 쓸 안내 }
export function nextAction(state) {
  const job = state.job;
  if (running(job)) {
    if (job.waiting_for === 'approve') return { id: 'job-primary', hint: '다음 → [게시 승인]을 누르면 테스트 페이지의 「댓글」을 누릅니다' };
    if (job.waiting_for === 'confirm') return { id: 'job-primary', hint: '크롬에서 직접 게시한 뒤 [게시했어요]를 누르세요' };
    return { id: null, hint: `진행 중 · ${job.state_label}` };
  }
  if (!state.videos.length) {
    if (state.loading) return { id: null, hint: '영상을 찾는 중…' };
    return state.tab === 'url'
      ? { id: 'resolve-btn', hint: '다음 → 주소를 넣고 [불러오기]를 누르세요' }
      : { id: 'search-btn', hint: '다음 → [영상 찾기]를 누르세요' };
  }
  const video = selectedVideo();
  if (!video) return { id: 'video-list', hint: '다음 → 목록에서 영상을 하나 고르세요' };

  if (isApproved(state)) {
    const blocker = startBlocker(state);
    if (!blocker) {
      const failed = job && job.finished && job.state === 'failed' && job.video_id === video.video_id;
      return { id: 'job-primary', hint: failed ? '다시 시도 → [브라우저에서 영상 열기]' : '다음 → [브라우저에서 영상 열기]' };
    }
    const target = state.ops ? state.ops.target : 'sandbox';
    if (video.commented && video.commented[target]) {
      return { id: 'video-list', hint: '게시 완료 · 다른 영상을 고르세요' };
    }
    return { id: null, hint: blocker };
  }
  if (analyzing(state)) return { id: null, hint: `AI가 분석·초안을 만드는 중 · ${WAIT_HINT}` };
  if (state.approving) return { id: null, hint: '승인하는 중…' };

  const ctx = state.context && state.context.video_id === state.selectedId ? state.context : null;
  if (state.runError && state.runError.kind === NO_CONCERN && !(ctx && ctx.transcript_source === 'manual')) {
    const pasted = $('transcript-text') && $('transcript-text').value.trim();
    return pasted
      ? { id: 'transcript-save', hint: '다음 → 붙여 넣은 자막을 [저장]하세요' }
      : { id: 'transcript-paste', hint: '다음 → 자막을 붙여 넣고 [저장]한 뒤 다시 분석하세요' };
  }
  const draft = draftFor(state);
  if (draft) {
    const result = checkResult(state);
    if (result && result.passed && draft.status !== 'superseded') {
      return { id: 'approve-btn', hint: '다음 → 초안을 읽고 [이 초안 승인]을 누르세요' };
    }
    if (result && !result.passed) {
      return { id: 'draft-edit', hint: '빨간 항목을 고치거나 [다른 초안 생성]을 누르세요' };
    }
    return { id: null, hint: '규칙 검사 중…' };
  }
  return { id: 'run-btn', hint: `다음 → [분석하고 초안 만들기] · ${WAIT_HINT}` };
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
  // 흐름 띠: 지금 단계의 설명 줄에 다음 행동, 나머지는 원래 설명
  for (const p of document.querySelectorAll('.progress .step-hint')) {
    const current = p.closest('.step').classList.contains('is-current');
    const text = current ? next.hint : p.dataset.default;
    if (p.textContent !== text) p.textContent = text;
    p.classList.toggle('is-next-hint', current);
  }
}

export function initNext() {
  subscribe(paint);
  // 글을 고치거나 자막을 붙여 넣는 순간(검사·저장 전에도) 다시 고른다
  for (const id of ['draft-text', 'transcript-text']) $(id).addEventListener('input', paint);
  $('tab-keyword').addEventListener('click', paint);
  $('tab-url').addEventListener('click', paint);
  // 단추의 disabled는 다른 칸이 상태와 함께 바꾸므로, 잠깐 뒤 한 번 더 맞춘다(타이머로 바뀌는 단추)
  setInterval(paint, 1000);
}
