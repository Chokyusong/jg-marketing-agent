// 흐름 띠와 03 작업 상자: 지금 사용자가 있는 단계를 밝힌다(UI_SPEC 2.3).
// 고르기 전 01, 고르면 02, 글 상자의 초안을 승인하면 03(5단계). 규칙 검사만 통과하면 02에 머물고
// 03 상자가 "승인 대기"를 알린다. 승인한 뒤와 게시 작업 중의 03 상자 문구·큰 버튼은 job.js(8단계)가 쓴다.
import { isApproved } from './draft.js';
import { getState, selectedVideo, subscribe } from './state.js';

function draftChecked(state) {
  const v = state.validation;
  const input = document.getElementById('draft-text');
  return Boolean(v && v.videoId === state.selectedId && input && v.text === input.value && v.result.passed);
}

export function initFlow() {
  const steps = [...document.querySelectorAll('.progress .step')];
  const title = document.getElementById('exec-title');
  const desc = document.getElementById('exec-desc');
  const paint = () => {
    const state = getState();
    const video = selectedVideo();
    const approved = Boolean(video) && isApproved(state);
    const checked = Boolean(video) && draftChecked(state);
    const current = approved ? 3 : video ? 2 : 1;
    for (const step of steps) {
      const n = Number(step.dataset.step);
      step.classList.toggle('is-current', n === current);
      step.classList.toggle('is-done', n < current);
      if (n === current) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    }
    const job = state.job;
    if (approved || (job && (!job.finished || job.video_id === state.selectedId))) {
      return; // 초안 승인 완료 뒤의 문구(작업 준비 완료·진행 단계)는 job.js가 쓴다
    } else if (checked) {
      title.textContent = '규칙 검사 통과 · 승인 대기';
      desc.textContent = `선택: ${video.title} — 02의 [이 초안 승인]을 누르면 실행 단계로 넘어갑니다. 게시 여부는 로그인된 사용자 본인이 결정합니다.`;
    } else if (video) {
      title.textContent = '초안 대기';
      desc.textContent = `선택: ${video.title} — 초안이 규칙 검사를 통과하고 승인돼야 열 수 있습니다. 게시 여부는 로그인된 사용자 본인이 결정합니다.`;
    } else {
      title.textContent = '영상 선택 대기';
      desc.textContent = '01에서 영상을 고르세요. 게시 여부는 로그인된 사용자 본인이 결정합니다.';
    }
  };
  subscribe(paint);
  // 글을 고치는 순간 통과·승인 표시를 내린다(검사는 입력이 멈춘 뒤에 다시 한다).
  document.getElementById('draft-text').addEventListener('input', paint);
}
