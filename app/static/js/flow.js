// 흐름 띠와 03 작업 상자: 지금 사용자가 있는 단계를 밝힌다.
// 2단계: 고르기 전 01, 고르면 02. 03(초안 검사 통과)은 6단계 이후에 켠다.
import { selectedVideo, subscribe } from './state.js';

export function initFlow() {
  const steps = [...document.querySelectorAll('.progress .step')];
  const title = document.getElementById('exec-title');
  const desc = document.getElementById('exec-desc');
  subscribe(() => {
    const video = selectedVideo();
    const current = video ? 2 : 1;
    for (const step of steps) {
      const n = Number(step.dataset.step);
      step.classList.toggle('is-current', n === current);
      step.classList.toggle('is-done', n < current);
      if (n === current) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    }
    if (video) {
      title.textContent = '초안 대기';
      desc.textContent = `선택: ${video.title} — 초안과 규칙 검사(5·6단계)가 끝나야 열 수 있습니다. 게시 여부는 로그인된 사용자 본인이 결정합니다.`;
    } else {
      title.textContent = '영상 선택 대기';
      desc.textContent = '01에서 영상을 고르세요. 게시 여부는 로그인된 사용자 본인이 결정합니다.';
    }
  });
}
