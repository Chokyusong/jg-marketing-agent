// ② 맨 위: 고른 영상 한 줄 요약(썸네일 · 제목 · 채널 · 올린 날짜 · [유튜브에서 보기]).
import { el, formatAgo, formatDay, formatViews, thumbnail, titleNode } from './format.js';
import { selectedVideo, subscribe } from './state.js';

export function initAnalysis() {
  const box = document.getElementById('selected-summary');
  let shown;
  subscribe(() => {
    const video = selectedVideo();
    if (video === shown) return; // 고른 영상이 그대로면 다시 그리지 않는다
    shown = video;
    box.replaceChildren();
    if (!video) {
      box.append(el('p', { class: 'empty-sm', text: '①에서 영상을 고르면 고민 한 줄과 댓글 초안이 자동으로 나옵니다.' }));
      return;
    }
    box.append(
      thumbnail(video),
      el('div', { title: video.title }, [
        titleNode(video.title), // 끝의 #태그는 흐리게
        el('span', { class: 'video-meta', text: [video.channel_title, formatViews(video.view_count)].filter(Boolean).join(' · ') }),
        el('span', { class: 'video-meta' }, [
          `올린 날짜 ${formatDay(video.published_at)} · ${formatAgo(video.published_at)}`,
          el('a', { href: video.url, target: '_blank', rel: 'noopener noreferrer', text: '유튜브에서 보기' }),
        ]),
      ]),
    );
  });
}
