// ② AI 분석 · 댓글 생성. 2단계에서는 선택한 영상만 따라 보여 준다(분석은 5단계에서 연결).
import { el, formatAgo, formatDate, formatViews } from './format.js';
import { selectedVideo, subscribe } from './state.js';

export function initAnalysis() {
  const box = document.getElementById('selected-summary');
  subscribe(() => {
    const video = selectedVideo();
    box.replaceChildren();
    if (!video) {
      box.append(el('p', { class: 'empty-sm', text: '①에서 영상을 고르면 여기에 표시됩니다.' }));
      return;
    }
    box.append(
      el('span', { class: 'thumb' }, [video.thumbnail_url ? el('img', { src: video.thumbnail_url, alt: '', referrerpolicy: 'no-referrer' }) : null]),
      el('div', {}, [
        el('p', { class: 'selected-title', text: video.title }),
        el('p', { class: 'selected-meta', text: `${video.channel_title} · ${formatViews(video.view_count)}` }),
        el('p', { class: 'selected-meta', title: formatDate(video.published_at), text: `올린 때 ${formatAgo(video.published_at)} (${formatDate(video.published_at)})` }),
        el('a', { href: video.url, target: '_blank', rel: 'noopener noreferrer', text: 'YouTube에서 보기' }),
      ]),
    );
  });
}
