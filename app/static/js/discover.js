// ① 영상 불러오기: [영상 불러오기](검색어 칸과 한 줄 거르기), 「영상 링크로 불러오기」, 영상 목록과 고르기.
// - 검색어 칸에 유튜브 주소를 넣고 [영상 불러오기]를 눌러도 그 영상 하나를 불러온다.
// - 링크로 불러온 영상은 목록 맨 위에 넣고 바로 고른다(고르면 ②가 자동으로 초안을 만든다).
// - 목록 한 줄: 썸네일 · 제목(끝의 #태그는 흐리게) · 채널 · 올린 날짜(11.17 · 7시간 전) · 조회수, 「댓글 달았음」.
import { api } from './api.js';
import { el, formatAgo, formatDay, formatViews, thumbnail, titleNode } from './format.js';
import { getState, setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);
const YOUTUBE_URL = /^(https?:\/\/)?((www|m|music)\.)?(youtube\.com|youtu\.be)\//i;

async function runSearch() {
  const query = $('q').value.trim();
  if (YOUTUBE_URL.test(query)) {
    runResolve(query); // 검색어 칸에 주소를 넣었으면 링크로 불러오기와 같게
    return;
  }
  setState({ loading: true, loadMode: 'search', error: null });
  try {
    const data = await api.searchVideos({
      q: query,
      period: $('period').value,
      order: $('order').value,
      maxResults: Number($('max-results').value),
      excludeShorts: $('exclude-shorts') ? $('exclude-shorts').checked : undefined,
    });
    if (!query) $('q').value = data.query;
    const keep = data.items.some((v) => v.video_id === getState().selectedId);
    setState({
      loading: false,
      videos: data.items,
      quota: data.quota,
      selectedId: keep ? getState().selectedId : null,
      meta: {
        mode: 'search', query: data.query, cached: data.cached, count: data.items.length,
        shortsExcluded: data.exclude_shorts ? data.shorts_excluded || 0 : null,
      },
    });
  } catch (error) {
    setState({ loading: false, error });
  }
}

async function runResolve(given) {
  const url = (given ?? $('video-url').value).trim();
  if (!url) {
    setState({ error: { message: '영상 주소를 넣어 주세요.', action: '예: https://youtu.be/영상ID' } });
    $('video-url').focus();
    return;
  }
  setState({ loading: true, loadMode: 'link', error: null });
  try {
    const data = await api.resolveVideo(url);
    const item = data.item;
    const rest = getState().videos.filter((v) => v.video_id !== item.video_id);
    setState({
      loading: false,
      videos: [item, ...rest],
      quota: data.quota,
      selectedId: item.video_id,
      meta: { ...(getState().meta || {}), mode: getState().meta ? getState().meta.mode : 'link', linked: true, count: rest.length + 1 },
    });
    if (given === undefined) $('video-url').value = '';
    const list = $('video-list');
    if (list) list.scrollTop = 0;
  } catch (error) {
    setState({ loading: false, error });
  }
}

// 7단계: 댓글을 단(게시 완료) 대상. 없으면 null
export function commentedText(commented) {
  if (!commented) return null;
  const where = [commented.sandbox ? '연습' : null, commented.youtube ? '유튜브' : null].filter(Boolean);
  if (!where.length) return null;
  return commented.youtube ? '댓글 달았음' : '댓글 달았음 · 연습';
}

function videoRow(video, selected) {
  const day = formatDay(video.published_at);
  const ago = formatAgo(video.published_at);
  const done = commentedText(video.commented);
  const body = el('span', { class: 'vid-body' }, [
    titleNode(video.title), // 끝의 #태그는 흐리게(원문은 title 속성에 그대로)
    el('span', { class: 'video-meta', text: video.channel_title || '' }),
    el('span', { class: 'video-meta' }, [
      day ? el('b', { class: 'vid-day', text: day }) : null,
      [ago, formatViews(video.view_count)].filter(Boolean).map((t) => ` · ${t}`).join(''),
    ]),
    done ? el('span', { class: 'commented', text: done }) : null,
  ]);
  return el(
    'button',
    { type: 'button', class: 'vid', 'aria-pressed': String(selected), 'data-id': video.video_id, title: video.title },
    [thumbnail(video), body],
  );
}

function renderList(state) {
  const list = $('video-list');
  list.setAttribute('aria-busy', String(state.loading));
  $('search-btn').disabled = state.loading;
  $('resolve-btn').disabled = state.loading;
  $('search-btn').textContent = state.loading && state.loadMode === 'search' ? '불러오는 중…' : '영상 불러오기';
  $('resolve-btn').textContent = state.loading && state.loadMode === 'link' ? '불러오는 중…' : '불러오기';

  const focusedId = document.activeElement?.dataset?.id;
  list.replaceChildren();
  if (!state.videos.length) {
    const text = state.loading
      ? '영상을 불러오는 중입니다… 보통 1~2초 걸립니다.'
      : state.meta
        ? '조건에 맞는 영상이 없습니다. 기간을 넓히거나 검색어를 바꿔 [영상 불러오기]를 다시 눌러 보세요.'
        : null;
    list.append(text ? el('p', { class: 'empty', text }) : el('p', { class: 'empty' }, [
      '기본 검색어가 들어 있습니다. ', el('b', { text: '[영상 불러오기]' }), '를 누르면 최신 영상이 뜹니다.',
    ]));
    return;
  }
  for (const video of state.videos) {
    list.append(videoRow(video, video.video_id === state.selectedId));
  }
  if (focusedId) list.querySelector(`[data-id="${CSS.escape(focusedId)}"]`)?.focus();
}

function renderMeta(state) {
  const meta = $('result-meta');
  meta.replaceChildren();
  if (!state.meta || state.loading) return;
  if (state.meta.mode === 'search') {
    meta.append(`‘${state.meta.query}’ 영상 ${state.meta.count}개`);
    // 실제 데이터 보정: 쇼츠(짧은 영상·길이 없음)를 뺀 수
    if (state.meta.shortsExcluded != null) {
      meta.append(el('span', { class: 'shorts-note', title: '짧은 영상(쇼츠)과 길이 정보가 없는 영상은 목록에서 뺍니다', text: `쇼츠 ${state.meta.shortsExcluded}개 뺌` }));
    }
    if (state.meta.cached) {
      meta.append(el('span', { class: 'shorts-note', title: '같은 검색은 10분 동안 앞서 불러온 결과를 다시 씁니다', text: '10분 안에 불러온 결과' }));
    }
  } else {
    meta.append('링크로 불러온 영상');
  }
  if (!state.selectedId && state.videos.length) meta.append(el('span', { class: 'pick-hint', text: '영상을 하나 고르세요' }));
}

function renderError(state) {
  const box = $('discover-error');
  if (!state.error) {
    box.hidden = true;
    return;
  }
  $('discover-error-msg').textContent = state.error.message || '요청을 처리하지 못했습니다.';
  $('discover-error-action').textContent = state.error.action || '';
  box.hidden = false;
}

function setupList() {
  const list = $('video-list');
  list.addEventListener('click', (event) => {
    const card = event.target.closest('.vid');
    if (!card) return;
    // 고르면 ②가 바로 분석·초안을 시작한다. 같은 영상을 다시 눌러도 그대로 둔다
    if (getState().selectedId !== card.dataset.id) setState({ selectedId: card.dataset.id });
  });
  list.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    const cards = [...list.querySelectorAll('.vid')];
    const i = cards.indexOf(document.activeElement);
    if (i < 0) return;
    event.preventDefault();
    cards[Math.min(cards.length - 1, Math.max(0, i + (event.key === 'ArrowDown' ? 1 : -1)))].focus();
  });
}

export function initDiscover() {
  // 「쇼츠 빼기」는 늘 기본값(discover.exclude_shorts)으로 시작한다. 창을 새로 고쳐도
  // 브라우저가 앞서 바꾼 체크 상태를 되살리지 않게 HTML의 처음 값으로 되돌린다(2026-11-17)
  const shorts = $('exclude-shorts');
  if (shorts) shorts.checked = shorts.defaultChecked;
  setupList();
  $('search-form').addEventListener('submit', (event) => {
    event.preventDefault();
    runSearch();
  });
  $('resolve-form').addEventListener('submit', (event) => {
    event.preventDefault();
    runResolve();
  });
  subscribe((state) => {
    renderList(state);
    renderMeta(state);
    renderError(state);
  });
}
