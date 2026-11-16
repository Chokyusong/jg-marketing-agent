// ① 영상 탐색: 탭, 검색창과 거르기(쇼츠 제외 포함), 영상 목록, 선택, 오류 문구.
import { api } from './api.js';
import { el, formatAgo, formatViews, thumbnail } from './format.js';
import { getState, setState, subscribe } from './state.js';

const $ = (id) => document.getElementById(id);

function setupTabs() {
  const tabs = [$('tab-keyword'), $('tab-url')];
  const panes = { keyword: $('pane-keyword'), url: $('pane-url') };

  const activate = (name, focus = false) => {
    setState({ tab: name, error: null });
    tabs.forEach((tab) => {
      const on = tab.id === `tab-${name}`;
      tab.setAttribute('aria-selected', String(on));
      tab.tabIndex = on ? 0 : -1;
      if (on && focus) tab.focus();
    });
    panes.keyword.hidden = name !== 'keyword';
    panes.url.hidden = name !== 'url';
  };

  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => activate(tab.id.replace('tab-', '')));
    tab.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      event.preventDefault();
      const next = tabs[(i + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
      activate(next.id.replace('tab-', ''), true);
    });
  });
}

async function runSearch() {
  const query = $('q').value.trim();
  setState({ loading: true, error: null });
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

async function runResolve() {
  const url = $('video-url').value.trim();
  if (!url) {
    setState({ error: { message: '영상 주소를 넣어 주세요.', action: '예: https://youtu.be/영상ID' } });
    $('video-url').focus();
    return;
  }
  setState({ loading: true, error: null });
  try {
    const data = await api.resolveVideo(url);
    setState({
      loading: false,
      videos: [data.item],
      quota: data.quota,
      selectedId: data.item.video_id,
      meta: { mode: 'link', count: 1, cached: false },
    });
  } catch (error) {
    setState({ loading: false, error });
  }
}

// 7단계: 댓글을 단(게시 완료) 대상. 없으면 null
export function commentedText(commented) {
  if (!commented) return null;
  const where = [commented.sandbox ? '테스트 페이지' : null, commented.youtube ? '유튜브' : null].filter(Boolean);
  return where.length ? `댓글 단 영상 · ${where.join('·')}` : null;
}

function videoRow(video, selected) {
  const meta = [video.channel_title, formatViews(video.view_count), formatAgo(video.published_at)].filter(Boolean);
  const done = commentedText(video.commented);
  const body = el('span', {}, [
    el('span', { class: 'video-title', text: video.title }),
    el('span', { class: 'video-meta' }, [
      done ? el('span', { class: 'commented', text: done }) : null,
      meta.join(' · '),
    ]),
  ]);
  return el(
    'button',
    { type: 'button', class: 'vid', 'aria-pressed': String(selected), 'data-id': video.video_id, title: video.title },
    [thumbnail(video), body, el('i', { class: 'pick', 'aria-hidden': 'true' })],
  );
}

function renderList(state) {
  const list = $('video-list');
  list.setAttribute('aria-busy', String(state.loading));
  $('search-btn').disabled = state.loading;
  $('resolve-btn').disabled = state.loading;
  $('search-btn').textContent = state.loading && state.tab === 'keyword' ? '찾는 중…' : '영상 찾기 ↗';
  $('resolve-btn').textContent = state.loading && state.tab === 'url' ? '불러오는 중…' : '불러오기 ↗';

  const focusedId = document.activeElement?.dataset?.id;
  list.replaceChildren();
  if (!state.videos.length) {
    // 9단계: 불러오는 중·결과 없음·처음 화면마다 문구와 다음 행동
    const text = state.loading
      ? (state.tab === 'url' ? '영상을 불러오는 중입니다… 보통 1~2초 걸립니다.' : '영상을 찾는 중입니다… 보통 1~2초 걸립니다.')
      : state.meta
        ? '조건에 맞는 영상이 없습니다. 업로드 기간을 넓히거나 검색어를 바꿔 [영상 찾기]를 다시 눌러 보세요.'
        : null;
    list.append(text ? el('p', { class: 'empty', text }) : emptyIntro(state.tab));
    return;
  }
  for (const video of state.videos) {
    list.append(videoRow(video, video.video_id === state.selectedId));
  }
  if (focusedId) list.querySelector(`[data-id="${CSS.escape(focusedId)}"]`)?.focus();
}

function emptyIntro(tab) {
  if (tab === 'url') {
    return el('p', { class: 'empty' }, [
      '유튜브 영상 주소를 넣고 ',
      el('b', { text: '[불러오기]' }),
      '를 누르면 그 영상 하나가 뜹니다.',
    ]);
  }
  return el('p', { class: 'empty' }, [
    '기본 검색어가 들어 있습니다. ',
    el('b', { text: '[영상 찾기]' }),
    '를 누르면 최신 영상이 뜹니다.',
  ]);
}

function renderMeta(state) {
  const meta = $('result-meta');
  meta.replaceChildren();
  if (!state.meta || state.loading) return;
  if (state.meta.mode === 'search') {
    meta.append(`‘${state.meta.query}’ 영상 ${state.meta.count}개`);
    // 실제 데이터 보정: 쇼츠(61초 미만·길이 없음)를 뺀 수
    if (state.meta.shortsExcluded != null) {
      meta.append(el('span', { class: 'shorts-note', title: '61초 미만 영상과 길이 정보가 없는 영상은 목록에서 뺍니다', text: `쇼츠 ${state.meta.shortsExcluded}개 제외` }));
    }
    if (state.meta.cached) {
      meta.append(el('span', { class: 'tag', title: '같은 검색은 10분 동안 저장한 결과를 씁니다(할당량 절약)', text: '10분 저장 결과 · SAVED' }));
    }
  } else {
    meta.append('링크로 불러온 영상');
  }
  if (state.selectedId) meta.append(el('span', { class: 'tag', text: '1개 선택됨 · SELECTED' }));
  else if (state.videos.length) meta.append(el('span', { class: 'pick-hint', text: '영상을 하나 고르세요' }));
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
    const id = card.dataset.id;
    setState({ selectedId: getState().selectedId === id ? null : id });
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
  setupTabs();
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
