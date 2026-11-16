// 흐름 띠와 03 작업 상자: 지금 사용자가 있는 단계를 밝힌다(UI_SPEC 2.3).
// 고르기 전 01, 고르면 02, 지금 글 상자의 초안이 규칙 검사를 통과하면 03(6단계).
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
    const checked = Boolean(video) && draftChecked(state);
    const current = checked ? 3 : video ? 2 : 1;
    for (const step of steps) {
      const n = Number(step.dataset.step);
      step.classList.toggle('is-current', n === current);
      step.classList.toggle('is-done', n < current);
      if (n === current) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    }
    if (checked) {
      title.textContent = '규칙 검사 통과';
      desc.textContent = `선택: ${video.title} — 초안이 규칙 검사를 통과했습니다. 승인과 실행은 다음 단계에서 연결합니다. 게시 여부는 로그인된 사용자 본인이 결정합니다.`;
    } else if (video) {
      title.textContent = '초안 대기';
      desc.textContent = `선택: ${video.title} — 초안이 규칙 검사를 통과해야 열 수 있습니다. 게시 여부는 로그인된 사용자 본인이 결정합니다.`;
    } else {
      title.textContent = '영상 선택 대기';
      desc.textContent = '01에서 영상을 고르세요. 게시 여부는 로그인된 사용자 본인이 결정합니다.';
    }
  };
  subscribe(paint);
  // 글을 고치는 순간 통과 표시를 내린다(검사는 입력이 멈춘 뒤에 다시 한다).
  document.getElementById('draft-text').addEventListener('input', paint);
}
