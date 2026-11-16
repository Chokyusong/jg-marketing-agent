// 서버 API 호출. 오류는 ApiError(kind, message, action)로 바꿔 던진다.

export class ApiError extends Error {
  constructor({ kind = 'unknown', message = '요청을 처리하지 못했습니다.', action = '', failures = [], fields = {} } = {}) {
    super(message);
    this.kind = kind;
    this.action = action;
    this.failures = failures; // 승인 거절(409)일 때 걸린 검사 항목
    this.fields = fields; // R2: 설정 저장이 거절(422)됐을 때 칸 이름 → 이유
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
      ...options,
    });
  } catch {
    throw new ApiError({
      kind: 'server_down',
      message: '프로그램 안의 서버에 연결하지 못했습니다.',
      action: '프로그램을 껐다가 다시 켜 주세요.',
    });
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    if (body && body.error) throw new ApiError(body.error);
    if (response.status === 422) {
      throw new ApiError({ kind: 'invalid_input', message: '입력값을 확인해 주세요.', action: '' });
    }
    throw new ApiError({ message: `서버 오류 (HTTP ${response.status})`, action: '잠시 뒤 다시 시도해 주세요.' });
  }
  return body;
}

export const api = {
  status: () => request('/api/status'),
  searchVideos: ({ q, period, order, maxResults, excludeShorts }) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (period) params.set('period', period);
    if (order) params.set('order', order);
    if (maxResults) params.set('max_results', String(maxResults));
    if (typeof excludeShorts === 'boolean') params.set('exclude_shorts', String(excludeShorts)); // 실제 데이터 보정
    const qs = params.toString();
    return request(`/api/videos${qs ? `?${qs}` : ''}`);
  },
  // R4: 뜨기 직전 영상(초안까지만). 쇼츠 빼기는 ①칸의 체크를 따른다
  risingVideos: ({ excludeShorts } = {}) => {
    const qs = typeof excludeShorts === 'boolean' ? `?exclude_shorts=${excludeShorts}` : '';
    return request(`/api/videos/rising${qs}`);
  },
  resolveVideo: (url) => request('/api/videos/resolve', { method: 'POST', body: JSON.stringify({ url }) }),
  // 3단계: 영상 맥락
  buildContext: (videoId, { refresh = false } = {}) =>
    request(`/api/videos/${encodeURIComponent(videoId)}/context${refresh ? '?refresh=true' : ''}`, { method: 'POST' }),
  saveTranscript: (videoId, text) =>
    request(`/api/videos/${encodeURIComponent(videoId)}/transcript`, { method: 'PUT', body: JSON.stringify({ text }) }),
  clearTranscript: (videoId) =>
    request(`/api/videos/${encodeURIComponent(videoId)}/transcript`, { method: 'DELETE' }),
  // 6단계: 규칙 검사 V1~V12
  validate: (videoId, text, disclose = true) =>
    request('/api/validate', { method: 'POST', body: JSON.stringify({ video_id: videoId, text, disclose }) }),
  // 5단계: 분석과 초안
  analyze: (videoId) => request(`/api/analysis/${encodeURIComponent(videoId)}`, { method: 'POST' }),
  storedAnalysis: (videoId) => request(`/api/analysis/${encodeURIComponent(videoId)}`),
  // disclose: 광고 표기를 붙일지(R3: 모든 영상에서 켜고 끈다)
  createDraft: (videoId, { another = false, disclose = true } = {}) =>
    request('/api/drafts', { method: 'POST', body: JSON.stringify({ video_id: videoId, another, disclose }) }),
  listDrafts: (videoId) => request(`/api/drafts?video_id=${encodeURIComponent(videoId)}`),
  updateDraft: (id, body) => request(`/api/drafts/${id}`, { method: 'PATCH', body: JSON.stringify({ body }) }),
  approveDraft: (id) => request(`/api/drafts/${id}/approve`, { method: 'POST' }),
  // R3: 광고 표기 켬/끔(저장된 글에서 표기만 바꾸고 다시 검사)
  setDisclosure: (id, disclose) =>
    request(`/api/drafts/${id}/disclosure`, { method: 'POST', body: JSON.stringify({ disclose }) }),
  // 7단계: 운영 규칙과 기록
  profiles: (target) => request(`/api/profiles?target=${encodeURIComponent(target)}`),
  records: (limit) => request(`/api/records?limit=${encodeURIComponent(limit)}`),
  todayStats: (target, dailyLimit) => {
    const params = new URLSearchParams({ target });
    if (dailyLimit) params.set('daily_limit', String(dailyLimit));
    return request(`/api/stats/today?${params}`);
  },
  // 8단계·R3: 게시 작업(실제 게시 · 연습 모드). approveJob은 게시 직전 확인(설정 켬)의 [게시]
  startJob: ({ videoId, draftId, profile, target, dailyLimit }) =>
    request('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({ video_id: videoId, draft_id: draftId, profile: profile || '', target, daily_limit: dailyLimit || null }),
    }),
  getJob: (id) => request(`/api/jobs/${encodeURIComponent(id)}`),
  approveJob: (id) => request(`/api/jobs/${encodeURIComponent(id)}/approve`, { method: 'POST' }),
  cancelJob: (id) => request(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  // 9단계: SETTINGS 패널(읽기 전용)과 [모델 미리 불러오기]
  settings: () => request('/api/settings'),
  warmup: () => request('/api/llm/warmup', { method: 'POST' }),
  // R2: 프로그램 안에서 설정 · API 키(값은 보내기만 하고 응답에는 없다) · 모델 목록 · 모니터
  saveSettings: (values) => request('/api/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
  resetSettings: () => request('/api/settings/reset', { method: 'POST' }),
  saveKey: (key) => request('/api/settings/youtube-key', { method: 'PUT', body: JSON.stringify({ key }) }),
  deleteKey: () => request('/api/settings/youtube-key', { method: 'DELETE' }),
  testKey: () => request('/api/settings/youtube-key/test', { method: 'POST' }),
  llmModels: () => request('/api/llm/models'),
  // R4: 모델이 메모리에 올라가 있는지(아니면 ②칸에 「불러오는 중」 안내)
  llmLoaded: () => request('/api/llm/loaded'),
  screens: () => request('/api/screens'),
  // R2: 프로필 로그인(크롬 창은 사람이 직접 로그인한다) · 로그인 확인(창 없이 읽기만)
  profileLogin: (name) => request(`/api/profiles/${encodeURIComponent(name)}/login`, { method: 'POST' }),
  profileCheck: (name) => request(`/api/profiles/${encodeURIComponent(name)}/check`, { method: 'POST' }),
  profileOpen: (name) => request(`/api/profiles/${encodeURIComponent(name)}/open`, { method: 'POST' }),
};
