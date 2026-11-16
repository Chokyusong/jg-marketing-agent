// 02 AI 분석과 댓글 초안. 2단계에서는 선택한 영상 카드만 따라 바뀐다(분석은 5단계에서 연결).
import { el, formatAgo, formatDate, formatViews, thumbnail } from './format.js';
import { selectedVideo, subscribe } from './state.js';

export function initAnalysis() {
  const box = document.getElementById('selected-summary');
  subscribe(() => {
    const video = selectedVideo();
    box.replaceChildren();
    if (!video) {
      box.append(el('p', { class: 'empty-sm', text: '01에서 영상을 고르면 여기에 표시됩니다.' }));
      return;
    }
    box.append(
      thumbnail(video),
      el('div', {}, [
        el('span', { class: 'video-title', text: video.title }),
        el('span', { class: 'video-meta', text: `선택한 영상 · ${video.channel_title} · ${formatViews(video.view_count)}` }),
        el('span', { class: 'video-meta', title: formatDate(video.published_at), text: `올린 때 ${formatAgo(video.published_at)} · ${formatDate(video.published_at)}` }),
        el('a', { href: video.url, target: '_blank', rel: 'noopener noreferrer', text: 'YouTube에서 보기 ↗' }),
      ]),
    );
  });
}
