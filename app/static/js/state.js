// 화면 상태는 여기 한 곳에 둔다. 칸들은 subscribe로 바뀐 상태를 받아 다시 그린다.

const state = {
  tab: 'keyword',        // 'keyword' | 'url'
  loading: false,
  error: null,           // { kind, message, action }
  videos: [],            // 목록에 보이는 영상
  meta: null,            // { query, cached, count, mode }
  selectedId: null,
  quota: null,           // { used_today, daily_limit }
  youtubeKey: null,      // true | false | null(모름)
};

const listeners = new Set();

export function getState() {
  return state;
}

export function setState(patch) {
  Object.assign(state, patch);
  for (const fn of listeners) fn(state);
}

export function subscribe(fn) {
  listeners.add(fn);
  fn(state);
  return () => listeners.delete(fn);
}

export function selectedVideo() {
  return state.videos.find((v) => v.video_id === state.selectedId) || null;
}
