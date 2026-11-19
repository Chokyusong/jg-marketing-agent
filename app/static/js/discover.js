// ① 영상 불러오기: [영상 불러오기](검색어 칸과 한 줄 거르기), 「영상 링크로 불러오기」, 영상 목록과 고르기.
// - 검색어 칸에 유튜브 주소를 넣고 [영상 불러오기]를 눌러도 그 영상 하나를 불러온다.
// - 링크로 불러온 영상은 목록 맨 위에 넣고 바로 고른다(고르면 ②가 자동으로 초안을 만든다).
// - 목록 한 줄: 썸네일 · 제목(끝의 #태그는 흐리게) · 채널 · 올린 날짜(11.17 · 7시간 전) · 조회수, 「댓글 달았음」.
// - R4 [뜨기 직전 영상]: 올린 지 34시간 안에 조회수가 빨리 오르는 영상(설정의 조건). 줄마다 「시간당 n회」와
//   「뜨기 직전」 표시. 이 목록에서 고른 영상도 다른 영상처럼 ③ [댓글 달기]로 달 수 있다(2026-11-19 대표 지시).
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

export function risingRuleText(rule) {
  if (!rule) return '';
  const n = (v) => Number(v).toLocaleString('ko-KR');
  return `조회수 ${n(rule.min_views)}~${n(rule.max_views)} · 시간당 ${n(rule.min_views_per_hour)}회 이상`;
}

async function runRising() {
  setState({ loading: true, loadMode: 'rising', error: null });
  try {
    const data = await api.risingVideos({
      excludeShorts: $('exclude-shorts') ? $('exclude-shorts').checked : undefined,
    });
    const keep = data.items.some((v) => v.video_id === getState().selectedId);
    setState({
      loading: false,
      videos: data.items,
      quota: data.quota,
      selectedId: keep ? getState().selectedId : null,
      meta: {
        mode: 'rising', query: data.query, cached: data.cached, count: data.items.length,
        rule: data.rising, checked: data.checked,
        shortsExcluded: data.exclude_shorts ? data.shorts_excluded || 0 : null,
      },
    });
  } catch (error) {
    setState({ loading: false, error });
  }
}

export function perHourText(value) {
  if (value === null || value === undefined) return '';
  return `시간당 ${Math.round(value).toLocaleString('ko-KR')}회`;
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

// 2026-11-18 자료가 얇은 영상: 이미 읽은 영상에만 「자막 있음」/「자막 없음」/「자료 부족」. 서버가 목록에
// 붙여 주고(video.transcript: yes·no·thin·빈 글), 이번에 고른 영상은 ② 자료가 오면 바로 바꾼다.
// 자막을 미리 읽지 않는다. 날짜 줄 높이를 지키려고 「자막 없음」의 뒷말(제목·설명·댓글로 씀)은 title로
const readTranscript = new Map();

function noteContext(state) {
  const ctx = state.context;
  if (ctx && ctx.video_id) {
    readTranscript.set(ctx.video_id, ctx.material || (ctx.transcript_source === 'none' ? 'no' : 'yes'));
  }
}

export function transcriptBadge(video) {
  const flag = readTranscript.get(video.video_id) || video.transcript || '';
  if (flag === 'yes') return el('span', { class: 'tbadge is-yes', text: '자막 있음' });
  if (flag === 'no') return el('span', { class: 'tbadge is-no', title: '자막 없음 · 제목·설명·댓글로 씀(초안이 밋밋할 수 있어요)', text: '자막 없음' });
  if (flag === 'thin') return el('span', { class: 'tbadge is-thin', title: '자료 부족 · 자막도 없고 설명·댓글도 거의 없어 제목만 읽어요', text: '자료 부족' });
  return null;
}

function videoRow(video, selected) {
  const day = formatDay(video.published_at);
  const ago = formatAgo(video.published_at);
  const done = commentedText(video.commented);
  const body = el('span', { class: 'vid-body' }, [
    titleNode(video.title), // 끝의 #태그는 흐리게(원문은 title 속성에 그대로)
    el('span', { class: 'video-meta', text: video.channel_title || '' }),
    // 2026-11-18: 좁은 칸(1366)에서 배지가 「자막 …」으로 잘렸다. 날짜 줄 글만 말줄임하고 배지는 그대로 둔다
    el('span', { class: 'video-meta has-badge' }, [
      el('span', { class: 'meta-text' }, [
        day ? el('b', { class: 'vid-day', text: day }) : null,
        [ago, formatViews(video.view_count)].filter(Boolean).map((t) => ` · ${t}`).join(''),
      ]),
      transcriptBadge(video),
    ]),
    video.rising ? el('span', { class: 'rising-line' }, [
      el('span', { class: 'rising-tag', text: '뜨기 직전' }),
      el('span', { class: 'rising-rate', text: perHourText(video.views_per_hour) }),
    ]) : null,
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
  $('rising-btn').disabled = state.loading;
  $('rising-btn').textContent = state.loading && state.loadMode === 'rising' ? '찾는 중…' : '뜨기 직전 영상';
  $('search-btn').textContent = state.loading && state.loadMode === 'search' ? '불러오는 중…' : '영상 불러오기';
  $('resolve-btn').textContent = state.loading && state.loadMode === 'link' ? '불러오는 중…' : '불러오기';

  const focusedId = document.activeElement?.dataset?.id;
  list.replaceChildren();
  if (!state.videos.length) {
    const rising = state.meta && state.meta.mode === 'rising';
    const text = state.loading
      ? '영상을 불러오는 중입니다… 보통 1~2초 걸립니다.'
      : rising
        ? `지금 조건에 맞는 영상이 없습니다(${risingRuleText(state.meta.rule)})`
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
  } else if (state.meta.mode === 'rising') {
    meta.append(`뜨기 직전 영상 ${state.meta.count}개`);
    meta.append(el('span', { class: 'shorts-note', title: `‘${state.meta.query}’ · 올린 지 34시간 안 · ${risingRuleText(state.meta.rule)}`, text: '올린 지 34시간 안' }));
    if (state.meta.cached) {
      meta.append(el('span', { class: 'shorts-note', title: '같은 요청은 10분 동안 앞서 불러온 결과를 다시 씁니다', text: '10분 안에 불러온 결과' }));
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
  $('rising-btn').addEventListener('click', () => runRising());
  subscribe((state) => {
    noteContext(state);
    renderList(state);
    renderMeta(state);
    renderError(state);
  });
}
