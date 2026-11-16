// 위 줄 진행 단계(UI_SPEC 0·2절): ① 영상 불러오기 → ② 영상 선택 → ③ 댓글 달기.
// 영상이 없으면 ①, 목록이 뜨면(고르기·초안 만드는 중) ②, 초안이 규칙 검사를 통과했거나 게시 중이면 ③.
// 좁은 창(1100px 아래, 세 칸을 탭으로)에서는 영상을 고를 때 ②, 게시를 시작하면 ③ 탭으로 넘긴다.
import { draftText } from './draft.js';
import { getState, selectedVideo, subscribe } from './state.js';
import { showColumn } from './topbar.js';

const NARROW = '(max-width: 1099px)';

function draftReady(state) {
  const v = state.validation;
  return Boolean(v && v.videoId === state.selectedId && v.text === draftText() && v.result.passed);
}

export function currentStep(state) {
  const video = selectedVideo();
  const job = state.job;
  const jobHere = job && (!job.finished || (video && job.video_id === video.video_id));
  if (jobHere || state.jobBusy || (video && draftReady(state))) return 3;
  if (state.videos.length) return 2;
  return 1;
}

export function initFlow() {
  const steps = [...document.querySelectorAll('.progress .step')];
  const narrow = window.matchMedia(NARROW);
  let lastSelected = null;
  let lastJobId = null;
  const paint = () => {
    const state = getState();
    const current = currentStep(state);
    for (const step of steps) {
      const n = Number(step.dataset.step);
      step.classList.toggle('is-current', n === current);
      step.classList.toggle('is-done', n < current);
      if (n === current) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    }
    if (state.selectedId !== lastSelected) {
      lastSelected = state.selectedId;
      if (state.selectedId && narrow.matches) showColumn(2);
    }
    const jobId = state.job && !state.job.finished ? state.job.id : null;
    if (jobId && jobId !== lastJobId && narrow.matches) showColumn(3);
    lastJobId = jobId || lastJobId;
  };
  subscribe(paint);
  // 글을 고치는 순간 통과 표시를 내린다(검사는 입력이 멈춘 뒤에 다시 한다).
  document.getElementById('draft-text').addEventListener('input', paint);
}
