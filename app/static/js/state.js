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
  // 3단계: 선택한 영상의 맥락 요약(POST /api/videos/{id}/context 응답)
  context: null,         // { video_id, transcript_source, transcript_chars, comment_count, comments_disabled, ... }
  contextLoading: false, // 맥락을 만들거나 자막을 저장하는 중
  contextError: null,    // { kind, message, action }
  // 6단계: 댓글 초안 규칙 검사(POST /api/validate 응답). 검사한 글과 함께 둔다
  validation: null,      // { videoId, text, result: { passed, char_count, checks: [...], ... } }
  validationLoading: false,
  validationError: null, // { kind, message, action }
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
