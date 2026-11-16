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
  // 4단계: 위 줄 AI 상태(GET /api/status의 ai). null이면 아직 모름
  ai: null,              // { provider, model, reachable, installed, local, error: {kind, message, action} | null }
  // 3단계: 선택한 영상의 맥락 요약(POST /api/videos/{id}/context 응답)
  context: null,         // { video_id, transcript_source, transcript_chars, comment_count, comments_disabled, ... }
  contextLoading: false, // 맥락을 만들거나 자막을 저장하는 중
  contextError: null,    // { kind, message, action }
  // 6단계: 댓글 초안 규칙 검사(POST /api/validate 응답). 검사한 글과 함께 둔다
  validation: null,      // { videoId, text, result: { passed, char_count, checks: [...], ... } }
  validationLoading: false,
  validationError: null, // { kind, message, action }
  // 5단계: 분석과 AI 초안. [분석하고 초안 만들기]를 눌러야 돈다(모델이 느려서 고르자마자 돌지 않는다)
  analysis: null,        // POST/GET /api/analysis/{id} 응답 { video_id, topic, concern, tone, viewer_needs, evidence: [...] }
  draft: null,           // 지금 글 상자에 넣은 초안(POST /api/drafts 응답) { id, video_id, body, status, validation, ... }
  run: null,             // { videoId, phase: 'context'|'analysis'|'draft'|'check'|'done'|'error', startedAt, endedAt, note }
  runError: null,        // { kind, message, action }
  approving: false,
  // 7단계: 오늘 통계·작업 기록·03칸 설정(ops.js). target은 작업 방식(sandbox | youtube)
  ops: null,             // { target, profile, dailyLimit, stats, records, total, error }
  // 8단계: 위 줄 BROWSER 상태(GET /api/status의 browser)와 03칸 게시 작업(job.js)
  browser: null,         // { chrome_found, playwright_ready, profiles: [{name, folder, exists}], active_job_id }
  job: null,             // GET /api/jobs/{id} 응답 { id, mode, target, state, step, finished, reason, ... }
  jobError: null,        // { kind, message, action } 시작·승인·확인이 거절됐을 때
  jobBusy: false,        // 시작·승인·확인 요청을 보내는 중
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
